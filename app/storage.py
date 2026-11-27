"""SQLite transaction boundary for the single-instance reference implementation."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import uuid
from app.domain import canonical_json, request_digest, utc_now

MIGRATIONS = Path(__file__).with_name('migrations')
SCHEMA_VERSION = 3
CONSUMER_NAME = 'local-ledger-projection-v1'


class IdempotencyConflict(Exception):
    pass


class ReversalConflict(Exception):
    pass


class LedgerStore:
    distributed = False

    def lock(self, conn, key):
        # SQLite serializes writers via BEGIN IMMEDIATE.
        pass

    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA foreign_keys = ON')
            conn.execute('PRAGMA busy_timeout = 5000')
            conn.execute('PRAGMA synchronous = FULL')
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def migrate(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute('PRAGMA journal_mode = WAL')
        with self.transaction() as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError('Database schema is newer than this application')
            for version in range(version + 1, SCHEMA_VERSION + 1):
                file = next(MIGRATIONS.glob(f'{version:03d}_*.sql'))
                statement = ''
                for line in file.read_text().splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        conn.execute(statement)
                        statement = ''
                if statement.strip():
                    raise RuntimeError(f'Incomplete migration: {file.name}')
                conn.execute(f'PRAGMA user_version = {version}')

    def ready(self):
        with self.connection() as conn:
            if conn.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
                return False
            for table in ('servicing_entries', 'audit_events', 'outbox', 'consumer_receipts', 'audit_archive_receipts'):
                conn.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone()  # nosec B608 - constant table allowlist
            return True

    @staticmethod
    def entry(row, replayed=False):
        data = dict(row)
        del data['idempotency_key'], data['request_hash']
        return {**data, 'idempotency_replayed': replayed}

    def record(self, key, payload, actor="local:writer", reversal_of=None):
        digest = request_digest(payload if reversal_of is None else {"reversal_of": reversal_of, **payload})
        with self.transaction() as conn:
            self.lock(conn, "idempotency:" + key)
            row = conn.execute('SELECT * FROM servicing_entries WHERE idempotency_key = ?',
                               (key,)).fetchone()
            if row:
                if row['request_hash'] != digest:
                    raise IdempotencyConflict
                return self.entry(row, True), False
            if reversal_of:
                self.lock(conn, "reversal:" + reversal_of)
                original = conn.execute('SELECT * FROM servicing_entries WHERE entry_id=?', (reversal_of,)).fetchone()
                if not original or original['reversal_of'] or conn.execute('SELECT 1 FROM servicing_entries WHERE reversal_of=?', (reversal_of,)).fetchone():
                    raise ReversalConflict
                payload = {**{k: original[k] for k in ('loan_ref','amount_cents','currency')}, **payload}
                if payload['effective_date'] < original['effective_date']:
                    raise ReversalConflict
            now = utc_now()
            entry_id, event_id = 'se_' + uuid.uuid4().hex, 'evt_' + uuid.uuid4().hex
            event = {'event_id': event_id, 'event_type': 'servicing.entry.recorded.v1',
                     'entry_id': entry_id, **payload, 'occurred_at': now, 'actor': actor, 'reversal_of': reversal_of}
            conn.execute('''INSERT INTO servicing_entries
                (entry_id,idempotency_key,request_hash,loan_ref,amount_cents,currency,
                 effective_date,state,created_at,reversal_of,reversal_reason) VALUES (?,?,?,?,?,?,?,'RECORDED',?,?,?)''',
                (entry_id, key, digest, payload['loan_ref'], payload['amount_cents'],
                 payload['currency'], payload['effective_date'], now, reversal_of, payload.get('reversal_reason')))
            conn.execute('INSERT INTO audit_events VALUES (?,?,?,?,?)',
                         ('aud_' + uuid.uuid4().hex, entry_id, 'servicing.entry.recorded',
                          now, canonical_json(event)))
            conn.execute('''INSERT INTO outbox
                (event_id,entry_id,event_type,payload_json,created_at) VALUES (?,?,?,?,?)''',
                (event_id, entry_id, event['event_type'], canonical_json(event), now))
            row = conn.execute('SELECT * FROM servicing_entries WHERE entry_id=?', (entry_id,)).fetchone()
            return self.entry(row), True

    def get(self, entry_id):
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM servicing_entries WHERE entry_id=?', (entry_id,)).fetchone()
            return self.entry(row) if row else None

    def reconciliation(self):
        """Consistent aggregate snapshot, not a financial balance reconciliation."""
        with self.connection() as conn:
            conn.execute('BEGIN')
            result = dict(conn.execute('''SELECT
                (SELECT count(*) FROM servicing_entries) AS entries,
                (SELECT count(*) FROM outbox WHERE handled_at IS NULL AND quarantined_at IS NULL) AS pending,
                (SELECT count(*) FROM outbox WHERE quarantined_at IS NOT NULL) AS quarantined,
                (SELECT count(*) FROM outbox WHERE handled_at IS NOT NULL) AS handled,
                (SELECT count(*) FROM outbox WHERE published_at IS NOT NULL AND handled_at IS NULL) AS awaiting_consumer,
                (SELECT count(*) FROM audit_events a WHERE NOT EXISTS (SELECT 1 FROM audit_archive_receipts r WHERE r.audit_id=a.audit_id)) AS unarchived_audit_events,
                (SELECT min(created_at) FROM outbox WHERE handled_at IS NULL AND quarantined_at IS NULL) AS oldest_pending_at,
                (SELECT count(*) FROM servicing_entries e WHERE
                    (SELECT count(*) FROM outbox o WHERE o.entry_id=e.entry_id) != 1 OR
                    (SELECT count(*) FROM audit_events a WHERE a.entry_id=e.entry_id AND a.event_type='servicing.entry.recorded') != 1) AS entry_integrity_errors,
                (SELECT count(*) FROM outbox o WHERE o.handled_at IS NOT NULL AND NOT EXISTS
                    (SELECT 1 FROM consumer_receipts r WHERE r.event_id=o.event_id AND r.consumer_name=?)) AS missing_receipts,
                (SELECT count(*) FROM consumer_receipts r WHERE r.consumer_name=? AND NOT EXISTS
                    (SELECT 1 FROM outbox o WHERE o.event_id=r.event_id AND o.handled_at IS NOT NULL)) AS unexpected_receipts
                ''', (CONSUMER_NAME, CONSUMER_NAME)).fetchone())
            result['status'] = 'attention_required' if any(result[k] for k in
                ('quarantined', 'entry_integrity_errors', 'missing_receipts', 'unexpected_receipts')) else 'ok'
            return result

    def balances(self, loan_ref):
        with self.connection() as conn:
            row = conn.execute("""SELECT count(*) AS entry_count,
                coalesce(sum(CASE WHEN reversal_of IS NULL THEN amount_cents ELSE 0 END),0) AS recorded_cents,
                coalesce(sum(CASE WHEN reversal_of IS NOT NULL THEN amount_cents ELSE 0 END),0) AS reversed_cents
                FROM servicing_entries WHERE loan_ref=?""", (loan_ref,)).fetchone()
            result = dict(row)
            return {**result, 'loan_ref': loan_ref, 'currency': 'USD', 'net_recorded_cents': result['recorded_cents']-result['reversed_cents']}


def make_store(settings):
    settings.validate_database()
    if settings.database_url:
        from app.postgres import PostgresStore
        return PostgresStore(settings.database_url)
    return LedgerStore(settings.db_path)


def storage_errors():
    try:
        import psycopg
        return (sqlite3.Error, psycopg.Error)
    except ImportError:
        return (sqlite3.Error,)
