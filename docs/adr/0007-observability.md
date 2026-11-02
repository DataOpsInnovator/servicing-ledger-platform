# ADR-0007: Managed-first observability

- **Status:** Accepted for MVP.
- **Context:** The project needs infra/API/business-process signals but must keep self-hosted operations and personal-account cost bounded.
- **Decision:** Start with CloudWatch for AWS-native logs/alarms and OpenTelemetry instrumentation; add a small Prometheus/Grafana layer only where it materially improves the demo.
- **Alternatives:** Full self-hosted Prometheus/Grafana/Loki; managed Prometheus/Grafana; Datadog or another SaaS.
- **Rationale:** A staged setup avoids running a monitoring platform larger than the workload while preserving portable instrumentation.
- **Consequences:** Vendor-native alert and query definitions may be less portable; self-hosted metrics require retention/cardinality controls.
- **Security / operations:** No sensitive business fields in telemetry; bounded metric labels; audit logs use separate retention and access controls.
- **Cost:** Managed ingestion and retention can dominate small-demo spend; estimate and cap retention.
- **Revisit when:** Required SLOs, query scale, or portability justify another backend.

