# Verification evidence — v2.0.0

Initial offline evidence source: previously delivered v1 ZIP, preserved separately. Verification environment Linux, Python 3.13.5; local preinstalled dependencies. No AWS credentials or infrastructure execution. Tests use synthetic fixtures, and injected errors/warnings are expected. No live dependency download, PostgreSQL installation, container runtime, Helm or Terraform binary available.

| Check | Result | Evidence |
|---|---|---|
| Python compile | PASS | `python -m compileall -q app tests scripts` |
| Local unit/HTTP tests | PASS — 34 passed, 4 skipped of 38 total | [v2-unit-tests.log](v2-unit-tests.log) |
| Live loopback smoke | PASS | [v2-smoke.log](v2-smoke.log) |
| 200-entry concurrency, worker drain, backup restoration | PASS — 200/200 created, 200 receipts, clean reconciliation | [v2-local-acceptance.log](v2-local-acceptance.log) |
| Static YAML/JSON parsing | PASS for untemplated manifests, workflow/Compose, values, Grafana | [v2-config-check.log](v2-config-check.log) |
| PostgreSQL integration (4 tests incl scoped roles), pg_dump/restore | PASS in GitHub Actions | [Main CI](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/runs/45938785505) |
| Real SQS / S3 / OIDC | NOT RUN — mocked SDK and signed-token tests only | local test log; cloud smoke and runbook |
| Terraform init/validate, Helm lint/render, Docker build, Compose configuration | PASS in GitHub Actions | [Main CI](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/runs/45938785505) |
| AWS plan/apply, live Helm deployment, container runtime acceptance | NOT RUN | Cloud deployment guide |
| Dependency/Bandit/image/IaC scanning, remote CI | PASS at configured thresholds | [Main CI](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/runs/45938785505) |
| Signed image, live Argo, Grafana and alerts | NOT RUN | configurations and release gates |
| RDS failover and PITR | NOT RUN | [operations guide](../operations-v2.md) |

Measured local timing is environment-specific, not a capacity benchmark; test pass count is not code coverage. AWS resource specifications passed provider validation in CI but still require live plan and staging acceptance; no AWS charge or compliance claim. `requirements.txt` pins observed dependency versions plus a PostgreSQL driver; fresh resolution and CVE scans are required. Prior v1 logs are historical, not v2 evidence. Do not represent configured controls as successfully deployed.

## GitHub validation record

- [PR #1](https://github.com/DataOpsInnovator/servicing-ledger-platform/pull/1), validated head `ca61214`, [pre-merge CI](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/runs/45938572156).
- Merge commit `ec5c72d1ba00e58ab7a95d0dc80f3932c2e46c54`, [post-merge CI](https://github.com/DataOpsInnovator/servicing-ledger-platform/actions/runs/45938785505): five jobs succeeded, including four PostgreSQL tests and matching restored schema/table fingerprints.
- Earlier offline logs remain unmodified. Remote CI results are point-in-time; the live AWS environment and organizational governance are not attested by these runs.
