import concurrent.futures
import json
import logging
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fastapi.testclient import TestClient
from app.config import Settings
from app.domain import EntryRequest
from app.outbox_worker import handle_batch
from app.servicing_api import create_app
from app.storage import LedgerStore, MIGRATIONS

PAYLOAD = dict(loan_ref='SYN-LOAN-0001', amount_cents=12500, currency='USD', effective_date='2026-11-02')
WRITER = 'w' * 40
OPERATOR = 'o' * 40
KEY = 'test-entry-0001'
PATH = '/v1/servicing-entries'
OPS = '/v1/operations/reconciliation'


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = LedgerStore(Path(self.temp.name) / 'ledger.db')
        self.client = TestClient(create_app(Settings(self.store.path, WRITER, OPERATOR)))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def post(self, payload=None, key=KEY, token=WRITER):
        return self.client.post(PATH, json=PAYLOAD if payload is None else payload,
                                headers={'Authorization': f'Bearer {token}', 'Idempotency-Key': key})

    def count(self, table):
        with self.store.connection() as conn:
            return conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]

    def test_create_read_and_replay(self):
        first = self.post()
        self.assertEqual(first.status_code, 201, first.text)
        body = first.json()
        self.assertEqual(body['state'], 'RECORDED')
        self.assertNotIn('request_hash', body)
        replay = self.post()
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()['entry_id'], body['entry_id'])
        self.assertTrue(replay.json()['idempotency_replayed'])
        get = self.client.get(first.headers['location'], headers={'Authorization': f'Bearer {OPERATOR}'})
        self.assertEqual(get.status_code, 200)
        self.assertEqual(get.json(), body)
        self.assertEqual([self.count(t) for t in ('servicing_entries','audit_events','outbox')], [1,1,1])

    def test_conflict_preserves_original(self):
        self.post()
        response = self.post(dict(PAYLOAD, amount_cents=999))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error'], 'IDEMPOTENCY_CONFLICT')
        self.assertEqual(self.count('servicing_entries'), 1)

    def test_concurrent_same_key(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.post(), range(16)))
        self.assertEqual([r.status_code for r in results].count(201), 1)
        self.assertEqual([r.status_code for r in results].count(200), 15)
        self.assertEqual(len({r.json()['entry_id'] for r in results}), 1)
        self.assertEqual([self.count(t) for t in ('servicing_entries','audit_events','outbox')], [1,1,1])

    def test_invalid_payloads_and_key(self):
        for patch in ({'amount_cents': True}, {'amount_cents': '100'}, {'amount_cents': 0},
                      {'amount_cents': 100000001}, {'loan_ref': 'REAL-00001'}, {'currency': 'EUR'},
                      {'effective_date': '2026-02-30'}, {'effective_date': '20261102'}, {'extra': 'x'}):
            with self.subTest(patch=patch):
                self.assertEqual(self.post(dict(PAYLOAD, **patch)).status_code, 400)
        self.assertEqual(self.post(key='short').status_code, 400)
        self.assertEqual(self.count('servicing_entries'), 0)

    def test_auth_and_roles(self):
        self.assertEqual(self.client.get(OPS).status_code, 401)
        self.assertEqual(self.post(token='incorrect').status_code, 401)
        self.assertEqual(self.post(token=OPERATOR).status_code, 403)
        self.assertEqual(self.client.get(OPS, headers={'Authorization': f'Bearer {WRITER}'}).status_code, 403)
        self.assertEqual(self.client.get(OPS, headers={'Authorization': f'Bearer {OPERATOR}'}).status_code, 200)
        self.assertEqual(self.client.get(PATH+'/unknown').status_code, 401)
        self.assertEqual(self.count('servicing_entries'), 0)

    def test_invalid_configuration_fails_startup(self):
        with self.assertRaises(ValueError):
            with TestClient(create_app(Settings(self.store.path, WRITER, WRITER))):
                pass

    def test_body_boundary(self):
        headers = {'Authorization': f'Bearer {WRITER}', 'Idempotency-Key': KEY}
        self.assertEqual(self.client.post(PATH, content='x', headers=headers).status_code, 415)
        headers['Content-Type'] = 'application/json'
        self.assertEqual(self.client.post(PATH, content=b'x'*16385, headers=headers).status_code, 413)
        self.assertEqual(self.client.post(PATH, content=iter([b'x'*9000,b'x'*9000]), headers=headers).status_code, 413)
        self.assertEqual(self.client.post(PATH, content='{invalid', headers=headers).status_code, 400)
        self.assertEqual(self.count('servicing_entries'), 0)

    def test_atomic_rollback(self):
        with self.store.connection() as conn:
            conn.execute("CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT,'injected'); END")
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual([self.count(t) for t in ('servicing_entries','audit_events','outbox')], [0,0,0])
        with self.store.connection() as conn:
            conn.execute('DROP TRIGGER fail_outbox')
        self.assertEqual(self.post().status_code, 201)

    def test_consumer_replay(self):
        self.post()
        self.assertEqual(handle_batch(self.store), 1)
        self.assertEqual(handle_batch(self.store), 0)
        with self.store.connection() as conn:
            conn.execute('UPDATE outbox SET handled_at=NULL')
        self.assertEqual(handle_batch(self.store), 0)
        self.assertEqual(self.count('consumer_receipts'), 1)
        self.assertEqual(self.count('audit_events'), 2)
        self.assertEqual(self.store.reconciliation()['status'], 'ok')

    def test_consumer_atomic_rollback(self):
        self.post()
        with self.store.connection() as conn:
            conn.execute("CREATE TRIGGER fail_receipt_audit BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.Error):
            handle_batch(self.store)
        self.assertEqual(self.count('consumer_receipts'), 0)
        self.assertEqual(self.store.reconciliation()['pending'], 1)
        with self.store.connection() as conn:
            conn.execute('DROP TRIGGER fail_receipt_audit')
        self.assertEqual(handle_batch(self.store), 1)

    def test_quarantine_does_not_block_valid_event(self):
        self.post()
        with self.store.connection() as conn:
            conn.execute("UPDATE outbox SET payload_json='invalid'")
        self.post(key='test-entry-0002')
        self.assertEqual(handle_batch(self.store), 1)
        report = self.store.reconciliation()
        self.assertEqual((report['quarantined'],report['handled'],report['pending']), (1,1,0))
        self.assertEqual(report['status'], 'attention_required')

    def test_reconciliation_detects_missing_receipt(self):
        self.post()
        handle_batch(self.store)
        with self.store.connection() as conn:
            conn.execute('DELETE FROM consumer_receipts')
        self.assertEqual(self.store.reconciliation()['missing_receipts'], 1)
        self.assertEqual(self.store.reconciliation()['status'], 'attention_required')

    def test_append_only_audit(self):
        self.post()
        for query in ('DELETE FROM audit_events', "UPDATE audit_events SET event_type='tampered'"):
            with self.assertRaises(sqlite3.IntegrityError):
                with self.store.connection() as conn:
                    conn.execute(query)
        self.assertEqual(self.count('audit_events'), 1)

    def test_readiness_and_liveness(self):
        self.assertEqual(self.client.get('/healthz').status_code, 200)
        self.assertEqual(self.client.get('/readyz').status_code, 200)
        with self.store.connection() as conn:
            conn.execute('PRAGMA user_version=0')
        self.assertEqual(self.client.get('/readyz').status_code, 503)
        self.assertEqual(self.client.get('/healthz').status_code, 200)

    def test_log_redaction(self):
        with self.assertLogs('servicing.api', logging.INFO) as logs:
            self.post()
        joined = '\n'.join(logs.output)
        for marker in (WRITER, KEY, PAYLOAD['loan_ref']):
            self.assertNotIn(marker, joined)
        self.assertIn('request_id', joined)

    def test_openapi_and_request_id(self):
        schema = self.client.get('/openapi.json').json()
        self.assertIn(PATH, schema['paths'])
        self.assertIn('HTTPBearer', schema['components']['securitySchemes'])
        response = self.post(token='bad')
        self.assertEqual(response.json()['request_id'], response.headers['x-request-id'])

    def test_missing_entry(self):
        response = self.client.get(PATH+'/se_'+'a'*32, headers={'Authorization': f'Bearer {WRITER}'})
        self.assertEqual(response.status_code, 404)

    def test_distinct_keys_create_distinct_entries(self):
        first, second = self.post(), self.post(key='test-entry-0002')
        self.assertNotEqual(first.json()['entry_id'], second.json()['entry_id'])
        self.assertEqual(self.count('servicing_entries'), 2)


class MigrationTests(unittest.TestCase):
    def test_upgrade_legacy_schema_preserves_data(self):
        with tempfile.TemporaryDirectory() as temp:
            store = LedgerStore(Path(temp)/'legacy.db')
            with store.connection() as conn:
                conn.executescript((MIGRATIONS/'001_initial.sql').read_text())
                conn.execute("INSERT INTO servicing_entries VALUES ('se_legacy','legacy-key','hash','SYN-LEGACY',100,'USD','2026-11-02','RECORDED',1,'now')")
            store.migrate()
            store.migrate()
            self.assertTrue(store.ready())
            self.assertEqual(store.get('se_legacy')['amount_cents'], 100)

    def test_backup_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            store = LedgerStore(Path(temp)/'source.db')
            store.migrate()
            entry, _ = store.record(KEY, EntryRequest(**PAYLOAD).model_dump())
            handle_batch(store)
            target = LedgerStore(Path(temp)/'restored.db')
            with store.connection() as source, target.connection() as dest:
                source.backup(dest)
            self.assertTrue(target.ready())
            self.assertEqual(target.get(entry['entry_id']), entry)
            self.assertEqual(target.reconciliation(), store.reconciliation())

    def test_future_schema_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            store = LedgerStore(Path(temp)/'future.db')
            with store.connection() as conn:
                conn.execute('PRAGMA user_version=99')
            with self.assertRaises(RuntimeError):
                store.migrate()


if __name__ == '__main__':
    unittest.main()
