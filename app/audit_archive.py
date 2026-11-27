"""Export append-only audit events to a versioned S3 Object Lock bucket."""
import argparse
import hashlib
import json
from app.config import Settings
from app.domain import canonical_json, utc_now
from app.storage import make_store


def archive_one(store, s3, bucket):
    from botocore.exceptions import ClientError
    with store.transaction() as conn:
        store.lock(conn, 'audit-archive-v1')
        row = conn.execute('''SELECT a.* FROM audit_events a WHERE NOT EXISTS
            (SELECT 1 FROM audit_archive_receipts r WHERE r.audit_id=a.audit_id)
            ORDER BY occurred_at,audit_id LIMIT 1''').fetchone()
        if not row:
            return False
        body = canonical_json(dict(row)).encode()
        key = 'audit/v1/'+row['audit_id']+'.json'
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType='application/json',
                          IfNoneMatch='*', ChecksumAlgorithm='SHA256', Metadata={'sha256':hashlib.sha256(body).hexdigest()})
        except ClientError as exc:
            if exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode') != 412:
                raise
            # A prior export may have succeeded before its receipt was committed.
            response = s3.get_object(Bucket=bucket, Key=key)
            with response['Body'] as stream:
                if stream.read(len(body)+1) != body:
                    raise RuntimeError('Audit archive object mismatch') from None
        conn.execute('INSERT INTO audit_archive_receipts VALUES (?,?) ON CONFLICT(audit_id) DO NOTHING', (row['audit_id'], utc_now()))
        return True


def main():
    import boto3
    from botocore.config import Config
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000:
        parser.error('limit must be between 1 and 10000')
    settings = Settings.from_env()
    if not settings.audit_bucket or not settings.database_url:
        parser.error('Configure AUDIT_BUCKET and PostgreSQL')
    store = make_store(settings)
    s3 = boto3.client('s3', config=Config(connect_timeout=3,read_timeout=10,retries={'total_max_attempts':1}))
    count = 0
    while count < args.limit and archive_one(store, s3, settings.audit_bucket):
        count += 1
    print(json.dumps({'event':'audit_archived','count':count}))


if __name__ == '__main__':
    main()
