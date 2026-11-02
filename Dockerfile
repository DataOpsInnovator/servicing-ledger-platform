FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERVICING_DB_PATH=/data/servicing.db \
    SERVICING_HOST=0.0.0.0 \
    SERVICING_PORT=8080

WORKDIR /app
COPY app/ /app/app/
RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app app \
    && mkdir -p /data \
    && chown -R 10001:10001 /app /data

USER 10001:10001
EXPOSE 8080
CMD ["python", "/app/app/servicing_api.py"]

