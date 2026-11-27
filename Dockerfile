# Keep the build tooling outside the final image; use patched Alpine packages.
FROM python:3.13.18-alpine3.24 AS base
RUN apk upgrade --no-cache
FROM base AS builder
WORKDIR /build
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --only-binary=:all: --target /opt/ledger-deps -r requirements.txt \
    && PYTHONPATH=/opt/ledger-deps python -m pip check
FROM base AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/ledger-deps \
    SERVICING_DB_PATH=/data/servicing.db SERVICING_HOST=0.0.0.0 SERVICING_PORT=8080
WORKDIR /app
# No runtime installer or bundled installer wheels are needed.
RUN python -m pip uninstall -y pip setuptools wheel \
    && rm -rf /usr/local/lib/python3.13/ensurepip \
    && addgroup -S -g 10001 app \
    && adduser -S -D -H -u 10001 -G app app \
    && mkdir -p /data && chown 10001:10001 /data
COPY --from=builder /opt/ledger-deps /opt/ledger-deps
COPY app/ /app/app/
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=2).close()"]
CMD ["python", "-m", "app.servicing_api"]
