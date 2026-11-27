"""SQS transactional outbox: at-least-once delivery, commit-before-ack consumer."""
import argparse
import json
import logging
import signal
import threading
import uuid

from app.config import Settings
from app.domain import canonical_json, utc_now
from app.storage import CONSUMER_NAME, make_store, storage_errors

LOGGER = logging.getLogger('servicing.queue')


def valid_event(row, body):
    try:
        event = json.loads(body)
        return (isinstance(event, dict) and event.get('event_id') == row['event_id']
                and event.get('entry_id') == row['entry_id'] and event.get('event_type') == row['event_type']
                and row['event_type'] == 'servicing.entry.recorded.v1'
                and canonical_json(event) == canonical_json(json.loads(row['payload_json'])))
    except (ValueError, TypeError):
        return False


def publish_one(store, sqs, queue_url):
    # Keep one row locked across the bounded SDK call. A crash after send but before
    # commit is safe: retry sends a duplicate, which the consumer deduplicates.
    with store.transaction() as conn:
        row = conn.execute('''SELECT * FROM outbox WHERE published_at IS NULL AND handled_at IS NULL
            AND quarantined_at IS NULL ORDER BY created_at,event_id LIMIT 1'''
            + (' FOR UPDATE SKIP LOCKED' if store.distributed else '')).fetchone()
        if not row:
            return False
        if not valid_event(row, row['payload_json']):
            conn.execute('UPDATE outbox SET quarantined_at=?,failure_code=? WHERE event_id=?',
                         (utc_now(), 'INVALID_EVENT', row['event_id']))
            return True
        sqs.send_message(QueueUrl=queue_url, MessageBody=row['payload_json'])
        conn.execute('UPDATE outbox SET published_at=? WHERE event_id=?', (utc_now(), row['event_id']))
        return True


def consume_message(store, body):
    try:
        event = json.loads(body)
        event_id = event['event_id']
        if not isinstance(event_id, str) or len(event_id) != 36:
            return False
    except (ValueError, TypeError, KeyError):
        return False
    with store.transaction() as conn:
        row = conn.execute('SELECT * FROM outbox WHERE event_id=?' + (' FOR UPDATE' if store.distributed else ''), (event_id,)).fetchone()
        if not row or row['quarantined_at'] or not valid_event(row, body):
            return False  # Let SQS redrive malformed/unrecognized messages to DLQ.
        now = utc_now()
        cursor = conn.execute('''INSERT INTO consumer_receipts VALUES (?,?,?)
            ON CONFLICT(consumer_name,event_id) DO NOTHING''', (CONSUMER_NAME, event_id, now))
        if cursor.rowcount == 1:
            conn.execute('INSERT INTO audit_events VALUES (?,?,?,?,?)', ('aud_'+uuid.uuid4().hex,
                row['entry_id'], 'servicing.entry.consumer_recorded', now, canonical_json({'event_id':event_id, 'event_type':row['event_type']})))
        conn.execute('UPDATE outbox SET handled_at=coalesce(handled_at,?) WHERE event_id=?', (now,event_id))
    return True


def receive_batch(store, sqs, queue_url):
    messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=5, WaitTimeSeconds=10,
                                   VisibilityTimeout=120).get('Messages', [])
    for message in messages:
        if consume_message(store, message['Body']):
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message['ReceiptHandle'])
        else:
            LOGGER.warning('{"event":"message_rejected_redrive_pending"}')
    return len(messages)


def main():
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=['publisher','consumer'])
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    settings = Settings.from_env()
    store = make_store(settings)
    if not settings.queue_url or not store.distributed:
        parser.error('SQS mode requires PostgreSQL and SQS_QUEUE_URL')
    if settings.auto_migrate:
        store.migrate()
    if not store.ready(full=False):
        raise RuntimeError('Database schema is not ready')
    sqs = boto3.client('sqs', config=Config(connect_timeout=3, read_timeout=15, retries={'total_max_attempts':1}))
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    delay = 1
    while not stop.is_set():
        try:
            count = publish_one(store, sqs, settings.queue_url) if args.role == 'publisher' else receive_batch(store, sqs, settings.queue_url)
            delay = 1
            if args.once:
                return 0
            if not count:
                stop.wait(delay)
        except storage_errors() + (BotoCoreError, ClientError) as exc:
            LOGGER.error(json.dumps({'event':'queue_worker_failure','role':args.role,'error_type':type(exc).__name__}))
            if args.once:
                return 1
            stop.wait(delay)
            delay = min(60, delay*2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
