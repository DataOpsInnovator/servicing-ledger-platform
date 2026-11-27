"""Offline database maintenance commands for synthetic data only."""
import argparse
import json
from pathlib import Path
import sqlite3
import re
import uuid
from app.domain import canonical_json, utc_now
from app.config import Settings
from app.storage import make_store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    migrate = sub.add_parser('migrate')
    migrate.add_argument('--grant-cloud-roles', action='store_true')
    sub.add_parser('reconcile')
    requeue = sub.add_parser('requeue')
    requeue.add_argument('event_id')
    requeue.add_argument('--incident', required=True)
    requeue.add_argument('--confirm-investigated', action='store_true', required=True)
    backup = sub.add_parser('backup')
    backup.add_argument('destination', type=Path)
    args = parser.parse_args()
    store = make_store(Settings.from_env())
    if args.command == 'migrate':
        store.migrate()
        if args.grant_cloud_roles:
            if not store.distributed:
                parser.error('Cloud roles require PostgreSQL')
            with store.transaction() as conn:
                conn.raw.execute(Path(__file__).with_name('grants.sql').read_text(), prepare=False)
        return
    if (not store.distributed and not store.path.is_file()) or not store.ready():
        parser.error('database is missing or not ready')
    if args.command == 'requeue':
        if not re.fullmatch(r'evt_[a-f0-9]{32}', args.event_id) or not re.fullmatch(r'[A-Za-z0-9-]{6,64}', args.incident):
            parser.error('Invalid event or incident identifier')
        with store.transaction() as conn:
            row = conn.execute('SELECT * FROM outbox WHERE event_id=?' + (' FOR UPDATE' if store.distributed else ''), (args.event_id,)).fetchone()
            if not row or row['handled_at'] or row['quarantined_at'] or not row['published_at']:
                parser.error('Only published, unhandled, nonquarantined events may be requeued')
            conn.execute('UPDATE outbox SET published_at=NULL WHERE event_id=?', (args.event_id,))
            conn.execute('INSERT INTO audit_events VALUES (?,?,?,?,?)', ('aud_'+uuid.uuid4().hex,row['entry_id'],'servicing.entry.requeue_requested',utc_now(),canonical_json({'event_id':args.event_id,'incident':args.incident})))
        print('Requeue requested; retain incident approval and monitor delivery')
        return
    if args.command == 'reconcile':
        report = store.reconciliation()
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report['status'] == 'ok' else 1)
    if store.distributed:
        parser.error("Use pg_dump or RDS snapshots/PITR for PostgreSQL")
    destination = args.destination
    if destination.resolve() == store.path.resolve():
        parser.error('backup cannot overwrite source')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental overwrites, including concurrent commands.
    with destination.open('xb'):
        pass
    try:
        target = sqlite3.connect(destination)
        try:
            with store.connection() as source:
                source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('backup integrity check failed')
        finally:
            target.close()
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    print('Backup created and SQLite integrity check passed')


if __name__ == '__main__':
    main()
