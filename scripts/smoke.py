"""Real HTTP + subprocess smoke test; generates ephemeral synthetic credentials and DB."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def run():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        writer, operator = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        env = dict(os.environ, SERVICING_DB_PATH=str(Path(temp)/'ledger.db'),
                   SERVICING_HOST='127.0.0.1', SERVICING_PORT=str(port),
                   SERVICING_WRITER_TOKEN=writer, SERVICING_OPERATOR_TOKEN=operator, SERVICING_ENV='local', AUTO_MIGRATE='true')
        for key in ('DATABASE_URL','DATABASE_SECRET_ARN','SQS_QUEUE_URL','OIDC_ISSUER','OIDC_AUDIENCE','OIDC_JWKS_URL','OTEL_EXPORTER_OTLP_ENDPOINT'):
            env.pop(key,None)
        def request(path, token=None, payload=None):
            headers = {'Authorization': f'Bearer {token}'} if token else {}
            if payload is not None:
                headers.update({'Content-Type': 'application/json', 'Idempotency-Key': 'smoke-entry-0001'})
            req = Request(f'http://127.0.0.1:{port}'+path,
                          data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
            try:
                with urlopen(req, timeout=3) as res:
                    return res.status, json.load(res)
            except HTTPError as exc:
                return exc.code, json.load(exc)
        with subprocess.Popen([sys.executable, '-m', 'app.servicing_api'], cwd=root, env=env) as api:
            try:
                for _ in range(60):
                    if api.poll() is not None:
                        raise RuntimeError('API exited before readiness')
                    try:
                        if request('/readyz')[0] == 200:
                            break
                    except (URLError, OSError):
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError('API not ready')
                payload = dict(loan_ref='SYN-SMOKE-0001', amount_cents=12500, currency='USD', effective_date='2026-11-02')
                path = '/v1/servicing-entries'
                status, first = request(path, writer, payload)
                assert status == 201, first
                status, replay = request(path, writer, payload)
                assert status == 200 and replay['entry_id'] == first['entry_id']
                assert request(path, writer, dict(payload, amount_cents=42))[0] == 409
                assert request(path+'/'+first['entry_id'])[0] == 401
                subprocess.run([sys.executable, '-m', 'app.outbox_worker', '--once'], cwd=root, env=env, check=True)
                status, report = request('/v1/operations/reconciliation', operator)
                assert status == 200 and report['handled'] == 1 and report['status'] == 'ok', report
                subprocess.run([sys.executable, '-m', 'app.admin', 'backup', str(Path(temp)/'backup.db')], cwd=root, env=env, check=True)
                print('PASS: live HTTP create/replay/conflict/auth, worker, reconciliation and backup')
            finally:
                api.terminate()
                api.wait(timeout=10)


if __name__ == '__main__':
    run()
