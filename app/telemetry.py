"""Bounded-cardinality metrics and optional OTLP traces (no financial payloads)."""
import os
from prometheus_client import CollectorRegistry, Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace


class Telemetry:
    def __init__(self):
        self.registry = CollectorRegistry()
        self.requests = Counter('ledger_http_requests_total','HTTP requests', ['method','route','status'], registry=self.registry)
        self.duration = Histogram('ledger_http_request_duration_seconds','Request duration', ['method','route'], registry=self.registry)
        self.backlog = Gauge('ledger_reconciliation_items','Reconciliation count', ['kind'], registry=self.registry)
        self.pending_age = Gauge('ledger_oldest_pending_seconds','Age of oldest pending outbox event', registry=self.registry)
        self.scrape_ok = Gauge('ledger_reconciliation_scrape_ok','Reconciliation query succeeded', registry=self.registry)
        self.tracer = trace.get_tracer('servicing-ledger')

    def observe(self, method, route, status, duration):
        self.requests.labels(method, route, str(status)).inc()
        self.duration.labels(method, route).observe(duration)

    def render(self):
        return generate_latest(self.registry), CONTENT_TYPE_LATEST


def configure_tracing():
    if os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT'):
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider = TracerProvider(resource=Resource.create({'service.name': 'servicing-ledger-api'}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        return provider
