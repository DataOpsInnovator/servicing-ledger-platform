"""Runtime settings. Cloud mode requires OIDC, TLS PostgreSQL and separate migrations."""
from dataclasses import dataclass, field
from pathlib import Path
import os
from urllib.parse import urlparse, parse_qs


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path('work/servicing.db')
    writer_token: str = field(default='', repr=False)
    operator_token: str = field(default='', repr=False)
    database_url: str = field(default='', repr=False)
    oidc_issuer: str = ''
    oidc_audience: str = ''
    oidc_jwks_url: str = ''
    environment: str = 'local'
    auto_migrate: bool = True
    queue_url: str = ''
    audit_bucket: str = ''

    @classmethod
    def from_env(cls):
        database_url = os.getenv('DATABASE_URL', '')
        secret_id = os.getenv('DATABASE_SECRET_ARN', '')
        if secret_id:
            if database_url:
                raise ValueError('Configure only one database credential source')
            import boto3
            from botocore.config import Config
            secret = boto3.client('secretsmanager', config=Config(connect_timeout=3, read_timeout=5, retries={'total_max_attempts':2})).get_secret_value(SecretId=secret_id)
            database_url = secret['SecretString']
        return cls(Path(os.getenv('SERVICING_DB_PATH', 'work/servicing.db')),
                   os.getenv('SERVICING_WRITER_TOKEN', ''), os.getenv('SERVICING_OPERATOR_TOKEN', ''),
                   database_url, os.getenv('OIDC_ISSUER', ''),
                   os.getenv('OIDC_AUDIENCE', ''), os.getenv('OIDC_JWKS_URL', ''),
                   os.getenv('SERVICING_ENV', 'local'), os.getenv('AUTO_MIGRATE', 'true').lower() == 'true',
                   os.getenv('SQS_QUEUE_URL', ''), os.getenv('AUDIT_BUCKET', ''))

    def validate_database(self):
        if self.environment not in ('local', 'cloud'):
            raise ValueError('Invalid environment')
        if self.database_url and urlparse(self.database_url).scheme not in ('postgresql', 'postgres'):
            raise ValueError('DATABASE_URL must be PostgreSQL')
        if self.environment == 'cloud':
            if not self.database_url or parse_qs(urlparse(self.database_url).query).get('sslmode') != ['verify-full']:
                raise ValueError('Cloud requires PostgreSQL sslmode=verify-full')
            if self.auto_migrate:
                raise ValueError('Cloud runtime cannot auto-migrate')

    def validate(self):
        self.validate_database()
        if self.oidc_issuer or self.oidc_jwks_url or self.oidc_audience or self.environment == 'cloud':
            if not (self.oidc_issuer.startswith('https://') and self.oidc_jwks_url.startswith('https://') and self.oidc_audience):
                raise ValueError('Configure HTTPS issuer/JWKS and audience')
            if self.writer_token or self.operator_token:
                raise ValueError('Do not mix OIDC and shared tokens')
        elif (min(len(self.writer_token), len(self.operator_token)) < 32 or self.writer_token == self.operator_token):
            raise ValueError('Configure distinct writer/operator tokens of at least 32 characters')
