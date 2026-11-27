"""Compare restored PostgreSQL schema and all journal rows in a quiesced disposable DB."""
import sys
import os
from app.postgres import PostgresStore
from app.domain import canonical_json
import hashlib


def snapshot(store):
    if not store.ready():
        raise RuntimeError('schema not ready')
    result = {}
    with store.connection() as conn:
        conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        for table, order in [('servicing_entries','entry_id'),('audit_events','audit_id'),('outbox','event_id'),('consumer_receipts','consumer_name,event_id'),('audit_archive_receipts','audit_id')]:
            digest = hashlib.sha256()
            count = 0
            for row in conn.execute(f'SELECT * FROM {table} ORDER BY {order}'):
                digest.update(canonical_json(dict(row)).encode()+b'\n')
                count += 1
            result[table] = (count,digest.hexdigest())
        conn.commit()
    return result


if __name__ == '__main__':
    source, target = sys.argv[1:] if len(sys.argv)==3 else (os.getenv('SOURCE_DATABASE_URL'), os.getenv('RESTORED_DATABASE_URL'))
    if not source or not target or source == target:
        raise SystemExit('Supply distinct source and restored DSNs via protected environment')
    if snapshot(PostgresStore(source)) != snapshot(PostgresStore(target)):
        raise SystemExit('FAIL: restored rows differ')
    print('PASS: restored schema and all five table fingerprints match')
