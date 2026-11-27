"""PostgreSQL adapter. Runtime uses a non-owner role; migration uses a separate owner."""
from contextlib import contextmanager
from pathlib import Path
from app.storage import LedgerStore, SCHEMA_VERSION


class Connection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        # Internal constant SQL only; no user-controlled SQL strings.
        return self.raw.execute(sql.replace('?', '%s'), params if params else None)

    def commit(self):
        self.raw.execute('COMMIT')

    def rollback(self):
        self.raw.execute('ROLLBACK')


class PostgresStore(LedgerStore):
    distributed = True

    def __init__(self, dsn):
        self.dsn = dsn

    @contextmanager
    def connection(self):
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row, connect_timeout=5,
                             options='-c statement_timeout=10000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=30000') as conn:
            yield Connection(conn)

    @contextmanager
    def transaction(self):
        with self.connection() as conn:
            conn.execute('BEGIN')
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def lock(self, conn, key):
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(?, 0))', (key,))

    def migrate(self):
        with self.transaction() as conn:
            self.lock(conn, 'ledger-schema-v1')
            conn.execute('CREATE TABLE IF NOT EXISTS ledger_schema (version integer PRIMARY KEY)')
            row = conn.execute('SELECT max(version) AS version FROM ledger_schema').fetchone()
            version = row['version'] or 0
            if version > SCHEMA_VERSION:
                raise RuntimeError('Database schema is newer than application')
            for n in range(version+1, SCHEMA_VERSION+1):
                path = next(Path(__file__).with_name('migrations_postgres').glob(f'{n:03d}_*.sql'))
                # psycopg permits multiple statements via simple query protocol with no parameters.
                conn.raw.execute(path.read_text(), prepare=False)
                conn.execute('INSERT INTO ledger_schema VALUES (?)', (n,))

    def ready(self, full=True):
        with self.connection() as conn:
            row = conn.execute('SELECT max(version) AS version FROM ledger_schema').fetchone()
            if row['version'] != SCHEMA_VERSION:
                return False
            if not full:
                return True
            for query in ('SELECT 1 FROM servicing_entries LIMIT 1',
                          'SELECT 1 FROM audit_events LIMIT 1',
                          'SELECT 1 FROM outbox LIMIT 1',
                          'SELECT 1 FROM consumer_receipts LIMIT 1',
                          'SELECT 1 FROM audit_archive_receipts LIMIT 1'):
                conn.execute(query)
            return True
