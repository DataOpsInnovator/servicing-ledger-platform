"""Real integration suite, opt-in via TEST_POSTGRES_DSN pointing to disposable DB."""
import concurrent.futures
import os
import unittest
from unittest.mock import Mock
from app.storage import ReversalConflict, IdempotencyConflict
from app.postgres import PostgresStore
from app.queue_worker import publish_one, consume_message
from test_ledger import PAYLOAD


@unittest.skipUnless(os.getenv('TEST_POSTGRES_DSN'), 'requires disposable PostgreSQL service')
class PostgreSQLIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = PostgresStore(os.environ['TEST_POSTGRES_DSN'])
        cls.store.migrate()
        cls.store.migrate()

    def test_distributed_idempotency_and_reversal(self):
        import uuid
        key = 'pg-'+uuid.uuid4().hex
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _:self.store.record(key,PAYLOAD),range(16)))
        self.assertEqual(sum(created for _,created in results),1)
        entry = results[0][0]
        with self.assertRaises(IdempotencyConflict):
            self.store.record(key,{**PAYLOAD,'amount_cents':1})
        def reverse(i):
            try:
                return self.store.record(key+'-'+str(i),{'effective_date':PAYLOAD['effective_date'],'reversal_reason':'DUPLICATE'},reversal_of=entry['entry_id'])[1]
            except ReversalConflict:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(reverse,range(12))),1)
        self.assertTrue(self.store.ready())
        self.assertEqual(self.store.balances(PAYLOAD['loan_ref'])['net_recorded_cents'],0)

    def test_real_transactions_and_fake_transport(self):
        import uuid
        self.store.record('pg-'+uuid.uuid4().hex,{**PAYLOAD,'loan_ref':'SYN-PG-EVENT'})
        sqs = Mock()
        while publish_one(self.store,sqs,'queue'):
            body = sqs.send_message.call_args.kwargs['MessageBody']
            self.assertTrue(consume_message(self.store,body))
            self.assertTrue(consume_message(self.store,body))
        self.assertEqual(self.store.reconciliation()['status'],'ok')

    def test_append_only_and_atomic_rollback(self):
        import psycopg
        import uuid
        key = 'pg-'+uuid.uuid4().hex
        entry,_ = self.store.record(key,{**PAYLOAD,'loan_ref':'SYN-PG-ROLLBACK'})
        with self.assertRaises(psycopg.Error), self.store.transaction() as c:
            c.execute('UPDATE servicing_entries SET amount_cents=1 WHERE entry_id=?',(entry['entry_id'],))
        self.assertEqual(self.store.get(entry['entry_id'])['amount_cents'],PAYLOAD['amount_cents'])
        with self.assertRaises(psycopg.Error), self.store.transaction() as c:
            c.execute('DELETE FROM audit_events WHERE entry_id=?',(entry['entry_id'],))
        with self.assertRaises(RuntimeError), self.store.transaction() as c:
            c.execute('INSERT INTO audit_events VALUES (?,?,?,?,?)',('aud_injected',entry['entry_id'],'test','now','{}'))
            raise RuntimeError('rollback')
        with self.store.connection() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM audit_events WHERE audit_id='aud_injected'").fetchone())

    def test_scoped_roles(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
        from pathlib import Path
        import uuid
        dsn = os.environ['TEST_POSTGRES_DSN']
        roles = ('api','publisher','consumer','archive','migrator')
        password = 'ci-'+uuid.uuid4().hex
        with psycopg.connect(dsn) as conn:
            for role in roles:
                name=sql.Identifier('ledger_'+role)
                conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(name,sql.Literal(password)))
                conn.execute(sql.SQL('ALTER ROLE {} SET search_path TO ledger, pg_catalog').format(name))
            conn.execute('CREATE SCHEMA ledger AUTHORIZATION ledger_migrator')
        stores={role:PostgresStore(make_conninfo(dsn,user='ledger_'+role,password=password)) for role in roles}
        stores['migrator'].migrate()
        with stores['migrator'].transaction() as c:
            c.raw.execute((Path(__file__).parents[1]/'app/grants.sql').read_text(),prepare=False)
        self.assertTrue(stores['api'].ready())
        entry,_=stores['api'].record('scoped-'+uuid.uuid4().hex,PAYLOAD)
        sqs=Mock()
        self.assertTrue(publish_one(stores['publisher'],sqs,'queue'))
        self.assertTrue(consume_message(stores['consumer'],sqs.send_message.call_args.kwargs['MessageBody']))
        self.assertEqual(stores['api'].reconciliation()['status'],'ok')
        for role,statement in [('api','DELETE FROM audit_events'),('publisher','SELECT * FROM servicing_entries'),('consumer','UPDATE outbox SET published_at=NULL'),('archive','INSERT INTO consumer_receipts VALUES (\'x\',\'x\',\'x\')')]:
            with self.subTest(role=role), self.assertRaises(psycopg.errors.InsufficientPrivilege), stores[role].transaction() as c:
                c.execute(statement)
