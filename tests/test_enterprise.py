import concurrent.futures
from datetime import datetime, timezone, timedelta
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

import jwt
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from app.auth import Authenticator, InvalidToken
from app.audit_archive import archive_one
from app.config import Settings
from app.queue_worker import publish_one, receive_batch, consume_message
from app.servicing_api import create_app
from app.storage import LedgerStore
from test_ledger import PAYLOAD, WRITER, OPERATOR, KEY, PATH


class EnterpriseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = LedgerStore(Path(temp.name)/'ledger.db')
        self.client = TestClient(create_app(Settings(self.store.path, WRITER, OPERATOR)))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def auth(self, token, key=KEY):
        return {'Authorization':'Bearer '+token, 'Idempotency-Key':key}

    def record(self):
        return self.client.post(PATH, json=PAYLOAD, headers=self.auth(WRITER)).json()

    def reverse(self, entry, key='reverse-0001', token=OPERATOR, **patch):
        return self.client.post(PATH+'/'+entry['entry_id']+'/reversal', headers=self.auth(token,key),
                                json={'reversal_reason':'DUPLICATE','effective_date':PAYLOAD['effective_date'],**patch})

    def test_reversal_replay_and_net(self):
        entry = self.record()
        self.assertEqual(self.reverse(entry,token=WRITER).status_code,403)
        rev = self.reverse(entry)
        self.assertEqual(rev.status_code,201,rev.text)
        self.assertEqual(rev.json()['reversal_of'],entry['entry_id'])
        self.assertEqual(self.reverse(entry).status_code,200)
        self.assertEqual(self.reverse(entry,reversal_reason='INCORRECT_AMOUNT').status_code,409)
        self.assertEqual(self.reverse(entry,key='reverse-0002').status_code,409)
        self.assertEqual(self.reverse(rev.json(),key='reverse-0003').status_code,409)
        balance = self.client.get('/v1/loans/'+PAYLOAD['loan_ref']+'/reconciliation',headers=self.auth(OPERATOR)).json()
        self.assertEqual(balance['net_recorded_cents'],0)
        self.assertEqual(balance['recorded_cents'],PAYLOAD['amount_cents'])
        self.assertEqual(balance['reversed_cents'],PAYLOAD['amount_cents'])
        self.assertIsNone(self.store.get(entry['entry_id'])['reversal_of'])

    def test_concurrent_distinct_reversals(self):
        entry = self.record()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda i:self.reverse(entry,key=f'reverse-{i:04}'), range(12)))
        self.assertEqual(sum(r.status_code==201 for r in responses),1)
        self.assertEqual(sum(r.status_code==409 for r in responses),11)

    def test_reversal_rejects_early_date(self):
        self.assertEqual(self.reverse(self.record(),effective_date='2020-01-01').status_code,409)

    def test_database_rejects_mismatched_reversal(self):
        import sqlite3
        entry = self.record()
        with self.assertRaises(sqlite3.IntegrityError), self.store.transaction() as c:
            c.execute("INSERT INTO servicing_entries (entry_id,idempotency_key,request_hash,loan_ref,amount_cents,currency,effective_date,state,created_at,reversal_of,reversal_reason) VALUES (?,?,?,?,?,?,?,'RECORDED',?,?,?)", ('se_invalid','key-invalid','hash',entry['loan_ref'],1,'USD',entry['effective_date'],'now',entry['entry_id'],'DUPLICATE'))

    def test_entries_append_only(self):
        import sqlite3
        self.record()
        with self.assertRaises(sqlite3.IntegrityError), self.store.connection() as c:
            c.execute('UPDATE servicing_entries SET amount_cents=1')

    def test_queue_retries_duplicate_and_commit_before_ack(self):
        self.record()
        sqs = Mock()
        # Sending may fail after the service received the message. DB must not mark published.
        sqs.send_message.side_effect = TimeoutError('simulated ambiguous send')
        with self.assertRaises(TimeoutError):
            publish_one(self.store,sqs,'queue')
        sqs.send_message.side_effect = None
        self.assertTrue(publish_one(self.store,sqs,'queue'))
        self.assertFalse(publish_one(self.store,sqs,'queue'))
        body = sqs.send_message.call_args.kwargs['MessageBody']
        sqs.receive_message.return_value = {'Messages':[{'Body':body,'ReceiptHandle':'receipt-1'}]}
        sqs.delete_message.side_effect = TimeoutError('simulated lost acknowledgement')
        with self.assertRaises(TimeoutError):
            receive_batch(self.store,sqs,'queue')
        self.assertEqual(self.store.reconciliation()['handled'],1)
        sqs.delete_message.side_effect = None
        self.assertEqual(receive_batch(self.store,sqs,'queue'),1)
        with self.store.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM consumer_receipts').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM audit_events').fetchone()[0],2)
        self.assertEqual(self.store.reconciliation()['status'],'ok')

    def test_tampered_queue_message_is_not_acknowledged(self):
        self.record()
        sqs = Mock()
        publish_one(self.store,sqs,'queue')
        body = json.loads(sqs.send_message.call_args.kwargs['MessageBody'])
        body['amount_cents'] = 1
        sqs.receive_message.return_value = {'Messages':[{'Body':json.dumps(body),'ReceiptHandle':'bad'}]}
        receive_batch(self.store,sqs,'queue')
        sqs.delete_message.assert_not_called()
        self.assertFalse(consume_message(self.store,'[]'))
        self.assertEqual(self.store.reconciliation()['handled'],0)

    def test_archive_conditional_put_retry(self):
        self.record()
        s3 = Mock()
        self.assertTrue(archive_one(self.store,s3,'bucket'))
        self.assertFalse(archive_one(self.store,s3,'bucket'))
        kwargs = s3.put_object.call_args.kwargs
        self.assertEqual(kwargs['IfNoneMatch'],'*')
        with self.store.connection() as c:
            c.execute('DELETE FROM audit_archive_receipts')
        s3.put_object.side_effect = ClientError({'ResponseMetadata':{'HTTPStatusCode':412},'Error':{'Code':'PreconditionFailed'}},'PutObject')
        s3.get_object.return_value = {'Body':io.BytesIO(kwargs['Body'])}
        self.assertTrue(archive_one(self.store,s3,'bucket'))
        self.assertEqual(self.store.reconciliation()['unarchived_audit_events'],0)
        with self.store.connection() as c:
            c.execute('DELETE FROM audit_archive_receipts')
        s3.get_object.return_value = {'Body':io.BytesIO(b'tampered')}
        with self.assertRaises(RuntimeError):
            archive_one(self.store,s3,'bucket')
        self.assertEqual(self.store.reconciliation()['unarchived_audit_events'],1)

    def test_metrics_cardinality_and_reconciliation(self):
        self.record()
        text = self.client.get('/metrics').text
        self.assertIn('ledger_reconciliation_items{kind="pending"} 1.0',text)
        self.assertNotIn(PAYLOAD['loan_ref'],text)
        self.assertNotIn(KEY,text)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.private = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.settings = Settings(oidc_issuer='https://id.example/',oidc_audience='ledger',oidc_jwks_url='https://id.example/jwks')
        self.jwks = Mock()
        self.jwks.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.private.public_key())
        self.auth = Authenticator(self.settings,self.jwks)

    def token(self, **patch):
        now = datetime.now(timezone.utc)
        return jwt.encode({'iss':self.settings.oidc_issuer,'aud':'ledger','sub':'synthetic-user','iat':now,
                           'exp':now+timedelta(minutes=5),'scope':'ledger:write',**patch},self.private,algorithm='RS256')

    def test_valid_scoped_token(self):
        p = self.auth.authenticate(self.token())
        self.assertEqual(p.roles,{'writer'})
        self.assertNotIn('synthetic-user',p.actor)
        self.assertEqual(self.auth.authenticate(self.token(scope='other')).roles,set())

    def test_reject_claims_signature_algorithm(self):
        for patch in ({'iss':'https://other/'},{'aud':'other'},{'exp':datetime.now(timezone.utc)-timedelta(minutes=1)},{'sub':''}):
            with self.subTest(patch=patch), self.assertRaises(InvalidToken):
                self.auth.authenticate(self.token(**patch))
        wrong = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        claims = jwt.decode(self.token(),options={'verify_signature':False})
        with self.assertRaises(InvalidToken):
            self.auth.authenticate(jwt.encode(claims,wrong,algorithm='RS256'))
        with self.assertRaises(InvalidToken):
            self.auth.authenticate(jwt.encode(claims,'x'*32,algorithm='HS256'))

    def test_cloud_fails_closed(self):
        for settings in (Settings(environment='cloud'),Settings(environment='cloud',database_url='postgresql://db/ledger?sslmode=require',auto_migrate=False),Settings(environment='cloud',database_url='postgresql://db/ledger?sslmode=verify-full',auto_migrate=False)):
            with self.assertRaises(ValueError):
                settings.validate()

    def test_signed_oidc_token_on_api(self):
        from dataclasses import replace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            settings = replace(self.settings, db_path=Path(temp)/'oidc.db')
            with patch('app.auth.jwt.PyJWKClient', return_value=self.jwks), TestClient(create_app(settings)) as client:
                writer = {'Authorization':'Bearer '+self.token(),'Idempotency-Key':'oidc-test-0001'}
                response = client.post(PATH,json=PAYLOAD,headers=writer)
                self.assertEqual(response.status_code,201,response.text)
                self.assertEqual(client.get('/v1/operations/reconciliation',headers=writer).status_code,403)
                operator = {'Authorization':'Bearer '+self.token(scope='ledger:operate')}
                self.assertEqual(client.get('/v1/operations/reconciliation',headers=operator).status_code,200)
                no_scope = {'Authorization':'Bearer '+self.token(scope='other')}
                self.assertEqual(client.get(PATH+'/'+response.json()['entry_id'],headers=no_scope).status_code,403)
                store=LedgerStore(settings.db_path)
                with store.connection() as c:
                    payload=json.loads(c.execute('SELECT payload_json FROM audit_events').fetchone()[0])
                    self.assertTrue(payload['actor'].startswith('oidc:'))
                    self.assertNotIn('synthetic-user',payload['actor'])
