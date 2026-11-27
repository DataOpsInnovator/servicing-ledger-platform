# Changelog

## 2.0.0 — Enterprise reference upgrade

- Added PostgreSQL adapter and transactional migrations, scoped database roles and opt-in integration/restore tests.
- Added immutable full reversal workflow, DB reversal integrity constraint, per-loan net journal reconciliation and pseudonymous OIDC actor attribution.
- Added RS256 OIDC access-token validation, cloud TLS fail-closed settings, role-scoped Secrets Manager credential loading.
- Implemented SQS publisher/consumer, lost-ack retry/deduplication, DLQ configuration and audited requeue. Added S3 Object Lock archive exporter and receipt tracking.
- Added AWS Terraform environment and remote-state bootstrap; digest-pinned Helm workloads, migration/archive jobs, network policies, PDB, optional HPA/ServiceMonitor and Argo templates.
- Added CI with PostgreSQL, backup restore, Terraform/Helm checks, scans; signed ECR release and SBOM; Prometheus rules, Grafana dashboard and optional OTLP request traces.
- Added repeatable local load and recovery acceptance, staging smoke, cloud deployment and recovery runbooks. Preserved v1 design as historical reference.
- Initial offline validation: 34 local tests passed, four PostgreSQL tests skipped, and 200-entry loopback acceptance/restore passed.
- Follow-up CI remediation aligned PostgreSQL 16 backup tools, upgraded dependencies, hardened KMS encryption and the non-root Alpine multi-stage image, and replaced dynamic SQL construction with static parameterized queries.
- All five jobs passed in [pre-merge CI](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/runs/45938572156) and [main CI](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/runs/45938785505); all four PostgreSQL integration tests and the five-table restore fingerprint check passed. Terraform/Helm validation and configured security scans passed. Live AWS deployment and signed artifact publication remain pending.
- Added Apache-2.0 licensing and updated publication documentation.

## 1.0.0 — Local reference modernization

- FastAPI, SQLite versioned migrations, transactional idempotency and outbox, role tokens, reconciliation, audit append-only controls and local worker.
- Unit tests and HTTP smoke, Docker/Helm local deployment definitions and engineering/operational documentation.
