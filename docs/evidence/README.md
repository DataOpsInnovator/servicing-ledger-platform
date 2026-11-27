# Verification evidence — v2.0.0

Source: previously delivered v1 ZIP, preserved separately. Verification environment Linux, Python 3.13.5; local preinstalled dependencies. No AWS credentials or infrastructure execution. Tests use synthetic fixtures, and injected errors/warnings are expected. No live dependency download, PostgreSQL installation, container runtime, Helm or Terraform binary available.

| Check | Result | Evidence |
|---|---|---|
| Python compile | PASS | `python -m compileall -q app tests scripts` |
| Local unit/HTTP tests | PASS — 34 passed, 4 skipped of 38 total | [v2-unit-tests.log](v2-unit-tests.log) |
| Live loopback smoke | PASS | [v2-smoke.log](v2-smoke.log) |
| 200-entry concurrency, worker drain, backup restoration | PASS — 200/200 created, 200 receipts, clean reconciliation | [v2-local-acceptance.log](v2-local-acceptance.log) |
| Static YAML/JSON parsing | PASS for untemplated manifests, workflow/Compose, values, Grafana | [v2-config-check.log](v2-config-check.log) |
| PostgreSQL integration (4 tests incl scoped roles), pg_dump/restore | NOT RUN — driver/server unavailable; configured CI | `.github/workflows/ci.yaml`, `tests/test_postgres.py` |
| Real SQS / S3 / OIDC | NOT RUN — mocked SDK and signed-token tests only | local test log; cloud smoke and runbook |
| Terraform init/validate/plan/apply, Helm lint/render, Docker build and startup | NOT RUN — tools unavailable | CI workflows, cloud deployment guide |
| Dependency/image/IaC scanning, signed image, remote CI, Argo, Grafana and alerts | NOT RUN | configurations and release gates |
| RDS failover and PITR | NOT RUN | [operations guide](../operations-v2.md) |

Measured local timing is environment-specific, not a capacity benchmark; test pass count is not code coverage. AWS resource specifications and infrastructure syntax require provider validation; no AWS charge or compliance claim. `requirements.txt` pins observed dependency versions plus a PostgreSQL driver; fresh resolution and CVE scans are required. Prior v1 logs are historical, not v2 evidence. Do not represent configured controls as successfully deployed.
