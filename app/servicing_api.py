"""Authenticated synthetic servicing API; run with python -m app.servicing_api."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
import re
import time
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException

from app.config import Settings
from app.domain import EntryRequest, EntryResponse, ErrorResponse, ReversalRequest
from app.storage import IdempotencyConflict, ReversalConflict, make_store, storage_errors
from app.auth import Authenticator, InvalidToken, Principal
from app.telemetry import Telemetry, configure_tracing

MAX_BODY_BYTES = 16_384
LOGGER = logging.getLogger('servicing.api')
BEARER = HTTPBearer(auto_error=False)


class RequestBoundary:
    """Bound request bodies even without Content-Length and emit safe correlation logs."""
    def __init__(self, app, telemetry):
        self.app = app
        self.telemetry = telemetry

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        scope.setdefault('state', {})['request_id'] = request_id
        started = time.monotonic()
        status = 500
        async def send_with_id(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                message['headers'] = list(message.get('headers', [])) + [
                    (b'x-request-id', request_id.encode()), (b'cache-control', b'no-store'),
                    (b'x-content-type-options', b'nosniff')]
            await send(message)
        async def reject(code, error):
            await JSONResponse({'error': error, 'request_id': request_id}, status_code=code)(
                scope, receive, send_with_id)
        span = self.telemetry.tracer.start_span("ledger.http")
        try:
            if scope['method'] == 'POST':
                headers = dict(scope['headers'])
                content_type = headers.get(b'content-type', b'').split(b';')[0].strip().lower()
                if content_type != b'application/json':
                    await reject(415, 'UNSUPPORTED_MEDIA_TYPE')
                    return
                body = bytearray()
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    chunk = message.get('body', b'')
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        await reject(413, 'BODY_TOO_LARGE')
                        return
                    body.extend(chunk)
                    if not message.get('more_body', False):
                        break
                delivered = False
                async def bounded_receive():
                    nonlocal delivered
                    if delivered:
                        return await receive()
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                await self.app(scope, bounded_receive, send_with_id)
            else:
                await self.app(scope, receive, send_with_id)
        finally:
            route = scope.get('route')
            span.set_attribute('http.route', getattr(route, 'path', 'unmatched'))
            span.set_attribute('http.response.status_code', status)
            span.end()
            self.telemetry.observe(scope['method'] if scope['method'] in ('GET','POST','HEAD') else 'OTHER', getattr(route, 'path', 'unmatched'), status, time.monotonic()-started)
            LOGGER.info(json.dumps({'event': 'http_request', 'request_id': request_id,
                'route': getattr(route, 'path', 'unmatched'), 'method': scope['method'],
                'status': status, 'duration_ms': round((time.monotonic()-started)*1000, 2)}))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = make_store(settings)
    telemetry = Telemetry()
    authenticator = Authenticator(settings)

    @asynccontextmanager
    async def lifespan(_app):
        settings.validate()
        if settings.auto_migrate:
            store.migrate()
        if not store.ready():
            raise RuntimeError("Database schema is not ready; run migrations first")
        provider = configure_tracing()
        try:
            yield
        finally:
            if provider:
                provider.shutdown()

    api = FastAPI(title='Servicing Ledger API', version='2.0.0', lifespan=lifespan,
                  description='Synthetic-only servicing entry recording. No funds movement.')
    api.add_middleware(RequestBoundary, telemetry=telemetry)

    def authenticate(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER)]):
        try:
            return authenticator.authenticate(credentials.credentials if credentials else '')
        except InvalidToken:
            raise HTTPException(401, 'UNAUTHORIZED', headers={'WWW-Authenticate': 'Bearer'}) from None

    def require_writer(principal: Annotated[Principal, Depends(authenticate)]):
        if 'writer' not in principal.roles:
            raise HTTPException(403, 'FORBIDDEN')
        return principal

    def require_operator(principal: Annotated[Principal, Depends(authenticate)]):
        if 'operator' not in principal.roles:
            raise HTTPException(403, 'FORBIDDEN')
        return principal

    def require_reader(principal: Annotated[Principal, Depends(authenticate)]):
        if not principal.roles:
            raise HTTPException(403, 'FORBIDDEN')
        return principal

    def error(request, status, code, headers=None):
        return JSONResponse({'error': code, 'request_id': request.state.request_id},
                            status_code=status, headers=headers)

    @api.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request, exc.status_code, exc.detail if isinstance(exc.detail, str)
                     else 'HTTP_ERROR', exc.headers)

    @api.exception_handler(RequestValidationError)
    async def validation_error(request, _exc):
        return error(request, 400, 'INVALID_REQUEST')

    async def storage_error(request, exc):
        LOGGER.error(json.dumps({'event': 'storage_failure', 'request_id': request.state.request_id,
                                 'error_type': type(exc).__name__}))
        return error(request, 503, 'TEMPORARY_STORAGE_FAILURE', {'Retry-After': '2'})

    for error_class in storage_errors():
        api.add_exception_handler(error_class, storage_error)

    @api.get('/healthz', tags=['health'])
    def health():
        return {'status': 'ok'}

    @api.get('/readyz', tags=['health'])
    def ready(response: Response):
        try:
            if store.ready():
                return {'status': 'ready'}
        except storage_errors():
            pass
        response.status_code = 503
        return {'status': 'not_ready'}

    @api.post('/v1/servicing-entries', status_code=201, response_model=EntryResponse,
              dependencies=[Depends(require_writer)], tags=['entries'],
              responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 409, 413, 415, 503)}
              | {200: {'model': EntryResponse, 'description': 'Idempotent replay'}})
    def create_entry(payload: EntryRequest, response: Response, principal: Annotated[Principal, Depends(require_writer)],
                     idempotency_key: Annotated[str | None, Header(alias='Idempotency-Key')] = None):
        if not idempotency_key or not re.fullmatch(r'[A-Za-z0-9._:-]{8,128}', idempotency_key):
            raise HTTPException(400, 'INVALID_IDEMPOTENCY_KEY')
        try:
            entry, created = store.record(idempotency_key, payload.model_dump(), principal.actor)
        except IdempotencyConflict:
            raise HTTPException(409, 'IDEMPOTENCY_CONFLICT') from None
        if created:
            response.headers['Location'] = '/v1/servicing-entries/' + entry['entry_id']
        else:
            response.status_code = 200
            response.headers['Idempotency-Replayed'] = 'true'
        return entry

    @api.get('/v1/servicing-entries/{entry_id}', response_model=EntryResponse,
             dependencies=[Depends(require_reader)], tags=['entries'])
    def get_entry(entry_id: str):
        entry = store.get(entry_id) if re.fullmatch(r'se_[a-f0-9]{32}', entry_id) else None
        if entry is None:
            raise HTTPException(404, 'NOT_FOUND')
        return entry

    @api.get('/v1/operations/reconciliation', dependencies=[Depends(require_operator)], tags=['operations'])
    def reconciliation():
        return store.reconciliation()

    @api.post('/v1/servicing-entries/{entry_id}/reversal', status_code=201, response_model=EntryResponse, tags=['entries'])
    def reverse(entry_id: str, payload: ReversalRequest, response: Response,
                principal: Annotated[Principal, Depends(require_operator)],
                idempotency_key: Annotated[str | None, Header(alias='Idempotency-Key')] = None):
        if not idempotency_key or not re.fullmatch(r'[A-Za-z0-9._:-]{8,128}', idempotency_key):
            raise HTTPException(400, 'INVALID_IDEMPOTENCY_KEY')
        if not re.fullmatch(r'se_[a-f0-9]{32}', entry_id):
            raise HTTPException(404, 'NOT_FOUND')
        try:
            entry, created = store.record(idempotency_key, payload.model_dump(), principal.actor, entry_id)
        except IdempotencyConflict:
            raise HTTPException(409, 'IDEMPOTENCY_CONFLICT') from None
        except ReversalConflict:
            raise HTTPException(409, 'REVERSAL_NOT_ALLOWED') from None
        if not created:
            response.status_code = 200
            response.headers['Idempotency-Replayed'] = 'true'
        else:
            response.headers['Location'] = '/v1/servicing-entries/' + entry['entry_id']
        return entry

    @api.get('/v1/loans/{loan_ref}/reconciliation', dependencies=[Depends(require_operator)], tags=['operations'])
    def loan_reconciliation(loan_ref: str):
        if not re.fullmatch(r'SYN-[A-Z0-9-]{4,40}', loan_ref):
            raise HTTPException(400, 'INVALID_LOAN_REFERENCE')
        return store.balances(loan_ref)

    @api.get('/metrics', include_in_schema=False)
    def metrics():
        try:
            report = store.reconciliation()
            for key in ('pending','quarantined','awaiting_consumer','unarchived_audit_events','entry_integrity_errors','missing_receipts','unexpected_receipts'):
                telemetry.backlog.labels(key).set(report[key])
            oldest = report['oldest_pending_at']
            telemetry.pending_age.set(max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(oldest)).total_seconds()) if oldest else 0)
            telemetry.scrape_ok.set(1)
        except storage_errors():
            telemetry.scrape_ok.set(0)
        body, content_type = telemetry.render()
        return Response(content=body, headers={'Content-Type': content_type})

    return api


app = create_app()


def main():
    import uvicorn
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    uvicorn.run(app, host=os.getenv('SERVICING_HOST', '127.0.0.1'),
                port=int(os.getenv('SERVICING_PORT', '8080')), access_log=False,
                server_header=False, limit_concurrency=100, timeout_keep_alive=5)


if __name__ == '__main__':
    main()
