# Servicing Ledger Platform

[![Ledger verification](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/workflows/ci.yaml) [![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**v2.0.0 | CI-validated financial-services reference implementation | AWS staging validation pending**

A business-oriented servicing journal for internal financial operations. It records synthetic servicing entries exactly once per stable idempotency key, maintains append-only audit history, handles downstream event retries, supports compensating reversals, and exposes reconciliation controls. It does not transfer funds, calculate loan balances or act as a general ledger. Never use customer data or real financial transactions in this reference implementation.

## Business problem and approach

A servicing operation must survive retries, preserve the original financial record and expose incomplete downstream work without creating duplicate entries. This project demonstrates an atomic journal/audit/outbox write, compensating reversals, scoped access and recoverable at-least-once event processing. It intentionally models one synthetic USD journal rather than a complete accounting or payment system.

## What is delivered

| Capability | Implementation | Verification status |
|---|---|---|
| API, integer USD cents, concurrent idempotency, atomic audit/outbox | FastAPI + SQLite/PostgreSQL adapter | SQLite and PostgreSQL integration verified in CI |
| Full compensating reversal, immutable originals, per-loan net journal amount | Role-gated API + DB constraint and unique index | Local verified |
| Identity | Local role tokens; RS256 OIDC access token issuer/audience/scope validation | Signed test tokens verified; real identity provider pending |
| Event processing | Local worker or SQS publisher and idempotent consumer; DLQ and audited requeue | Simulated SDK failure/replay verified; AWS pending |
| Audit archive | S3 conditional writes and Object Lock COMPLIANCE infrastructure | Mock SDK verified; live retention pending |
| Infrastructure | Terraform for two-AZ VPC, EKS, RDS, ECR, SQS, IAM, Secrets Manager, CloudWatch and state | Terraform init/validate and IaC scan passed; AWS plan/apply pending |
| Delivery | CI, dependency and image scan gates, signed ECR release, SBOM, reviewed Argo CD digest promotion | CI and container scan passed; signed ECR release and live Argo promotion pending |
| Operations | Prometheus metrics/rules, Grafana dashboard, optional OTLP spans, recovery/incident guides | Local metrics and restore verified; hosted monitoring pending |

See [current architecture](docs/architecture-v2.md), [business requirements](docs/business-requirements.md), [cloud deployment](docs/cloud-deployment.md), [operational runbook](docs/operations-v2.md), and [validation evidence](docs/evidence/README.md). Earlier architecture and portfolio documents are historical design references, not v2 deployment instructions.

## Verified engineering evidence

The enterprise modernization was merged in [PR #1](https://github.com/DataOpsInnovator/servicing-ledger-platform/pull/1). All five jobs passed in the [pre-merge run](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/runs/45938572156) and [post-merge run](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/runs/45938785505) on commit `ec5c72d`. These runs verify Python 3.12/3.13 application tests and acceptance, four PostgreSQL integration tests, dump/restore fingerprints, dependency audit, Bandit, Terraform validation and configuration scanning, Helm lint/render, Docker build/image scanning and Compose configuration. Scan results are point-in-time and apply to the configured thresholds and exceptions. See [evidence register](docs/evidence/README.md) for boundaries.

## Architecture

```mermaid
flowchart LR
  Client[Internal servicing client] -->|HTTPS / scoped OIDC| API[FastAPI replicas]
  API -->|Atomic insert| DB[(RDS PostgreSQL Multi-AZ)]
  DB --> PUB[Outbox publisher]
  PUB --> Q[SQS standard queue]
  Q --> CON[Consumer replicas]
  Q -. poison messages .-> DLQ[Dead-letter queue]
  CON -->|Receipt + audit + handled marker| DB
  DB --> ARC[Audit archive job]
  ARC --> WORM[S3 Object Lock archive]
  API --> MET[Prometheus / Grafana]
  Q --> CW[CloudWatch / SNS]
```

Local mode uses a shared SQLite file and in-process database-backed worker, with no AWS account required. PostgreSQL Compose mode replaces SQLite with PostgreSQL but still uses the local worker. Cloud mode uses distinct database/IAM principals for API, publisher, consumer, archive and migrations.

## Quick start (local, no AWS charges)

Requires Python 3.12 or 3.13; install dependencies in an isolated virtual environment. Dependencies are version-pinned, but fresh install and CVE scans must pass CI before release.

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/smoke.py
python -m scripts.local_acceptance
```

The default test run skips four tests requiring disposable PostgreSQL. The acceptance script creates its own temporary DB, tokens and API subprocess, sends 200 concurrent synthetic writes, drains the outbox and verifies a restored SQLite backup.

For a persistent interactive local session, generate two different URL-safe tokens of at least 32 characters:

```powershell
$env:SERVICING_WRITER_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:SERVICING_OPERATOR_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
python -m app.servicing_api
```

Bash equivalent: `export SERVICING_WRITER_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"` and repeat for `SERVICING_OPERATOR_TOKEN`. Open http://127.0.0.1:8080/docs; in another terminal in the same working directory run `python -m app.outbox_worker`.

## API examples

Authorize with `Bearer <writer-token>` in Swagger UI. Generate a unique `Idempotency-Key` for each intended operation (8–128 ASCII letters, digits or `. _ : -`). Example body for `POST /v1/servicing-entries`:

```json
{"loan_ref":"SYN-DEMO-0001","amount_cents":12500,"currency":"USD","effective_date":"2026-01-01"}
```

Expected: `201`, replay with same key/body returns `200` and same ID; changed body with same key returns `409`. Save the returned `entry_id`. Switch to the operator token for `POST /v1/servicing-entries/{entry_id}/reversal` using a new idempotency key:

```json
{"reversal_reason":"DUPLICATE","effective_date":"2026-01-01"}
```

The original remains unchanged. `GET /v1/loans/SYN-DEMO-0001/reconciliation` returns 12,500 recorded cents, 12,500 reversed cents, net zero. For corrections, reverse the erroneous entry and create the correct entry with a new key. These are distinct operations; do not assume atomic correction across two HTTP requests.

| Endpoint | Access |
|---|---|
| `POST /v1/servicing-entries` | writer / `ledger:write` |
| `GET /v1/servicing-entries/{entry_id}` | writer or operator |
| `POST /v1/servicing-entries/{entry_id}/reversal` | operator / `ledger:operate` |
| `GET /v1/loans/{loan_ref}/reconciliation` | operator |
| `GET /v1/operations/reconciliation` | operator |
| `/healthz`, `/readyz`, `/metrics` | internal only; cloud ingress excludes them |

## PostgreSQL locally

Install Docker and Compose. Copy `.env.example` to `.env` and set all three unique disposable credentials (use URL-safe generated password). Run `docker compose -f compose.postgres.yaml up --build`. This mode uses unencrypted loopback/container-network database traffic **only for local synthetic data** and a single database owner credential. Never expose it remotely. To exercise the real integration tests against a fresh disposable DB (they create roles/schema and write data), set `TEST_POSTGRES_DSN=postgresql://ledger:YOUR_URL_SAFE_PASSWORD@127.0.0.1:5432/ledger` in your shell, stop the API/worker, and run `python -m unittest discover -s tests -p test_postgres.py -v`. Prefer a separate fresh PostgreSQL instance with no application data; integration tests assume initial test data and a role-creating admin. Do not run against RDS or a shared database.

## AWS staging and GitOps

Read the [deployment guide](docs/cloud-deployment.md) before running Terraform. AWS infrastructure incurs charges, and the audit bucket enforces non-removable retention. The supplied Terraform passed provider validation in CI; a reviewed AWS plan, actual deployment and staging acceptance remain required. No cloud resources have been created by the repository author.

```text
app/                     API, auth, migrations, DB adapters, SQS and audit workers
scripts/                 bootstrap, smoke, load, restore validation
infra/terraform/state/   state-bucket bootstrap
infra/terraform/aws/     AWS environment Terraform
infra/terraform/portfolio/ historical v1 reference
deploy/helm/servicing-ledger/ local chart (single instance)
deploy/helm/ledger-cloud/     cloud chart (digest-pinned deployments, jobs, policies)
deploy/gitops/               Argo CD project and application templates
deploy/observability/        Prometheus, Grafana and optional collector templates
.github/workflows/       validation and signed release
tests/                  unit, HTTP, failure and opt-in PostgreSQL integration
docs/                   architecture, runbooks, evidence, ADRs and historical designs
```

## Acceptance and boundaries

Local evidence is recorded under `docs/evidence/`. The 200-entry run is a bounded loopback experiment, not an SLA or capacity benchmark. The target SLO, recovery objectives and compliance requirements are proposed, not certified. External identity, actual SQS delivery and DLQ behavior, RDS failover/PITR, object-lock retention, live Helm/EKS installation, Terraform plan/apply, signed release, and alert routing need execution and independent review. The CI validation and security scans described above have passed; they do not establish production compliance. The project deliberately remains single-organization, synthetic USD journal, and does not implement double-entry accounting, segregation-of-duties approval, consumer business side effects or integration with a source servicing system.

## Governance and license

See [contribution guidelines](CONTRIBUTING.md), [security policy](SECURITY.md), [release governance](docs/repository-governance.md) and [changelog](CHANGELOG.md). Repository-owned source is licensed under [Apache License 2.0](LICENSE); third-party dependencies retain their respective licenses.
