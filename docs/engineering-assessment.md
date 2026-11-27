# Engineering assessment and release decision

> **Historical v1.0 reference.** Preserved for design and portfolio context. For current implementation, see [v2 architecture](architecture-v2.md) and the root README. Statements about unimplemented PostgreSQL/SQS/reversals or old test counts describe v1 only.


## Executive decision

The supplied repository was a useful architecture-oriented portfolio scaffold, with a two-script local demonstration, a disposable Helm chart and substantial AWS design documentation. Its central transaction pattern was sound for the simulator, but the implementation lacked authentication, validation evidence, schema evolution, CI and recovery tooling. This release changes that into a tested local business-service reference. It is **not approved for production or real financial data**.

| Area | Original | Modernized | Remaining risk |
|---|---|---|---|
| API | ThreadingHTTPServer, manual parsing | FastAPI, typed contracts, OpenAPI, role checks, request IDs | Shared tokens; no enterprise identity, TLS or rate limiting |
| Transactions | Atomic SQLite writes, idempotency | Explicit repository, closed connections, migrations, concurrent and rollback tests | Single writer DB; no PostgreSQL verification or tenant identity |
| Audit | Application append-only convention | Update/delete triggers and tests | Privileged DB access can bypass; no independent immutable archive or individual actor |
| Outbox | Local receipt dedup | Quarantine, backoff, replay and rollback tests | No broker publisher or distributed delivery; no automatic redrive |
| Operations | Health probes | Reconciliation, structured logs, backup CLI, restore test | No monitored SLO, alerts, traces, tested failover or financial balance reconciliation |
| Delivery | Dockerfile and starter Helm | Dependency pins, Compose, hardened Helm options, CI gates | Container and CI unexecuted; action tags and base image not digest pinned |
| Infrastructure | Terraform README and AWS architecture | Preserved as roadmap | No executable Terraform or managed services |
| Governance | Detailed portfolio docs | Business requirements, runbook, security/contribution policy and evidence | Actual service owners, controls, reviews and release approvals unassigned |

## Prioritized production-readiness backlog

| Priority | Work package | Exit evidence |
|---|---|---|
| P0 | Product and control scope: business operation identifier, actor, corrections/reversals, monetary reconciliation, retention | Approved requirements and control mapping; independent review |
| P0 | PostgreSQL repository, schema migration, concurrency and isolation | Integration tests under real database, backup and restore evidence |
| P0 | Managed OIDC/workload identity, least privilege, TLS, secret rotation, threat model | Identity authorization and penetration test evidence |
| P0 | Independent audit export, encryption, and operational access review | Tamper-resistant evidence and access review |
| P0 | Executable Terraform for isolated dev, network, KMS, RDS, queue and budgets | Reviewed plan, policy gates, approved cost estimate and teardown |
| P1 | Real SQS publisher and consumer with retry/redrive and dedup | Crash-window, duplicate, poison and replay tests against real broker |
| P1 | Build and delivery hardening | CI green; CVE scan, image SBOM, digest/SHA pins, provenance and signing |
| P1 | Kubernetes deployment, alerts, traces, backup and failure exercises | Rendered/deployed manifests, alert tests, restore/failover results |
| P1 | Load and capacity validation, SLOs, on-call ownership | Measured latency/throughput and error budgets; reviewed runbooks |
| P2 | Multi-AZ and optional warm standby / GitOps promotion | Recovery and rollback evidence, justified against business requirements |

## Decisions taken during modernization

Keep synthetic data, original API resource and idempotency semantics. Choose FastAPI and SQLite rather than introduce an untested database adapter; use a single instance with two role tokens; keep the AWS architecture as a future target. Define this service as an entry journal rather than claiming an accounting ledger. Preserve original interview materials but separate them from engineering documentation. Do not add a license or invented organization/owner without user approval. No infrastructure was created and no public repository was modified.
