"""Local transactional consumer, not a distributed SQS publisher."""
import argparse
import json
import logging
import signal
import threading
import uuid

from app.config import Settings
from app.domain import canonical_json, utc_now
from app.storage import CONSUMER_NAME, LedgerStore, make_store, storage_errors

LOGGER = logging.getLogger('servicing.worker')


def handle_batch(store: LedgerStore, limit: int = 50) -> int:
    if not 1 <= limit <= 500:
        raise ValueError('batch limit must be 1–500')
    handled = 0
    with store.transaction() as conn:
        rows = conn.execute('''SELECT * FROM outbox WHERE handled_at IS NULL
            AND quarantined_at IS NULL ORDER BY created_at,event_id LIMIT ?''' + (' FOR UPDATE SKIP LOCKED' if store.distributed else ''), (limit,)).fetchall()
        for row in rows:
            now = utc_now()
            try:
                event = json.loads(row['payload_json'])
                if (not isinstance(event, dict) or event.get('event_id') != row['event_id']
                    or event.get('entry_id') != row['entry_id']
                    or event.get('event_type') != row['event_type']
                    or row['event_type'] != 'servicing.entry.recorded.v1'):
                    raise ValueError('invalid event envelope')
            except (ValueError, TypeError):
                conn.execute('UPDATE outbox SET quarantined_at=?,failure_code=? WHERE event_id=?',
                             (now, 'INVALID_EVENT', row['event_id']))
                LOGGER.warning(json.dumps({'event': 'outbox_quarantined', 'event_id': row['event_id']}))
                continue
            cursor = conn.execute('''INSERT INTO consumer_receipts VALUES (?,?,?)
                ON CONFLICT(consumer_name,event_id) DO NOTHING''', (CONSUMER_NAME, row['event_id'], now))
            if cursor.rowcount == 1:
                conn.execute('INSERT INTO audit_events VALUES (?,?,?,?,?)',
                             ('aud_' + uuid.uuid4().hex, row['entry_id'], 'servicing.entry.consumer_recorded',
                              now, canonical_json({'event_id': row['event_id'], 'event_type': row['event_type']})))
                handled += 1
            conn.execute('UPDATE outbox SET handled_at=? WHERE event_id=?', (now, row['event_id']))
    return handled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--poll-seconds', type=float, default=2)
    args = parser.parse_args()
    if not 0 < args.poll_seconds <= 300:
        parser.error('--poll-seconds must be in (0, 300]')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    settings = Settings.from_env()
    store = make_store(settings)
    if settings.queue_url:
        parser.error("Use app.queue_worker for SQS mode")
    if settings.auto_migrate:
        store.migrate()
    if not store.ready():
        raise RuntimeError("Database schema not ready")
    delay = args.poll_seconds
    while not stop.is_set():
        try:
            count = handle_batch(store)
            if count:
                LOGGER.info(json.dumps({'event': 'outbox_processed', 'count': count}))
            delay = args.poll_seconds
        except storage_errors() as exc:
            LOGGER.error(json.dumps({'event': 'worker_storage_failure', 'error_type': type(exc).__name__}))
            if args.once:
                return 1
            delay = min(60, delay * 2)
        if args.once:
            return 0
        stop.wait(delay)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
