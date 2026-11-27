"""Repeatable local load + worker drain + SQLite backup/restore acceptance."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request,urlopen
from app.config import Settings
from app.storage import LedgerStore
from scripts.load_test import run


def main():
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'ledger.db'
        with socket.socket() as s:
            s.bind(('127.0.0.1',0))
            port=s.getsockname()[1]
        writer,operator=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        env=dict(os.environ,SERVICING_DB_PATH=str(path),SERVICING_WRITER_TOKEN=writer,SERVICING_OPERATOR_TOKEN=operator,
                 SERVICING_HOST='127.0.0.1',SERVICING_PORT=str(port),SERVICING_ENV='local',AUTO_MIGRATE='true')
        for key in ('DATABASE_URL','DATABASE_SECRET_ARN','SQS_QUEUE_URL','OIDC_ISSUER','OIDC_AUDIENCE','OIDC_JWKS_URL','OTEL_EXPORTER_OTLP_ENDPOINT'):
            env.pop(key,None)
        base=f'http://127.0.0.1:{port}'
        api=subprocess.Popen([sys.executable,'-m','app.servicing_api'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(80):
                if api.poll() is not None:
                    raise RuntimeError('API startup failed')
                try:
                    with urlopen(base+'/readyz',timeout=1) as response:
                        if response.status==200:
                            break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('API not ready')
            run(base,writer,200,8)
            store=LedgerStore(path)
            for _ in range(5):
                subprocess.run([sys.executable,'-m','app.outbox_worker','--once'],env=env,check=True)
                if not store.reconciliation()['pending']:
                    break
            report=store.reconciliation()
            assert report['entries']==200 and report['handled']==200 and report['pending']==0 and report['status']=='ok',report
            backup=Path(temp)/'backup.db'
            subprocess.run([sys.executable,'-m','app.admin','backup',str(backup)],env=env,check=True)
            restored=LedgerStore(backup)
            assert restored.ready() and restored.reconciliation()==report
            print('PASS: 200 synthetic entries, 200 receipts, clean reconciliation, SQLite backup restored')
        finally:
            api.terminate()
            api.wait(timeout=15)


if __name__=='__main__':
    main()
