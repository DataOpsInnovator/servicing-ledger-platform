"""One-time PostgreSQL role setup from an approved VPC admin runner.
Does not print passwords or write them to disk. Refuses existing runtime roles.
If interrupted, follow cloud deployment runbook; do not blindly rerun.
"""
import argparse
import json
import secrets
from urllib.parse import quote, urlencode

ROLES = ('api','publisher','consumer','archive','migrator')


def main():
    import boto3
    import psycopg
    from psycopg import sql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admin-secret-arn', required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--runtime-secret-arns-json', required=True, help='Path to terraform output -json database_secret_arns')
    parser.add_argument('--ca-file', required=True, help='Trusted RDS CA bundle on admin runner')
    args = parser.parse_args()
    sm = boto3.client('secretsmanager')
    from pathlib import Path
    arns = json.loads(Path(args.runtime_secret_arns_json).read_text())
    if set(arns) != set(ROLES):
        parser.error('Expected exactly the five workload secret ARNs')
    master = json.loads(sm.get_secret_value(SecretId=args.admin_secret_arn)['SecretString'])
    passwords = {r: secrets.token_urlsafe(40) for r in ROLES}
    with psycopg.connect(host=args.endpoint, dbname='ledger', user=master['username'], password=master['password'],
                         sslmode='verify-full', sslrootcert=args.ca_file, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)', (['ledger_'+r for r in ROLES],))
            if cur.fetchall():
                raise RuntimeError('Workload roles already exist; use documented credential rotation/recovery procedure')
            cur.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
            cur.execute('REVOKE CONNECT ON DATABASE ledger FROM PUBLIC')
            for role in ROLES:
                name = sql.Identifier('ledger_'+role)
                cur.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}').format(name, sql.Literal(passwords[role])))
                cur.execute(sql.SQL('GRANT CONNECT ON DATABASE ledger TO {}').format(name))
                cur.execute(sql.SQL('ALTER ROLE {} IN DATABASE ledger SET search_path TO ledger, pg_catalog').format(name))
            # RDS administrator needs membership to assign ownership; remove after creation.
            master_ident = sql.Identifier(master['username'])
            cur.execute(sql.SQL('GRANT ledger_migrator TO {}').format(master_ident))
            cur.execute('CREATE SCHEMA ledger AUTHORIZATION ledger_migrator')
            cur.execute(sql.SQL('REVOKE ledger_migrator FROM {}').format(master_ident))
    # DB transaction commits before AWS writes. If interrupted, rotate affected role credentials manually.
    for role in ROLES:
        query = urlencode({'sslmode':'verify-full','sslrootcert':'/etc/rds-ca/global-bundle.pem'})
        dsn = f'postgresql://ledger_{role}:{quote(passwords[role], safe="")}@{args.endpoint}:5432/ledger?{query}'
        sm.put_secret_value(SecretId=arns[role], SecretString=dsn)
    print('Created five scoped database roles and populated Secrets Manager; run migration Job next.')


if __name__ == '__main__':
    main()
