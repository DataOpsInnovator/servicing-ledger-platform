# Implementation roadmap, validation, and demonstration

## Implementation tiers

| Tier | Scope | Deployment posture |
|---|---|---|
| Minimum viable portfolio | Synthetic entry API; idempotency; transaction + audit + outbox; duplicate-safe local worker; DB migrations and tests; local container; reproducible demo; security and architecture docs | Local by default; optional short-lived one-region AWS dev stack after cost gates |
| Advanced implementation | PostgreSQL adapter, SQS/DLQ, EKS, Terraform modules, OIDC CI, image provenance, Argo CD, policy gates, dashboards, restore rehearsal, controlled canary | Deploy only in tagged/time-limited personal account windows |
| Enterprise reference | Multi-account landing zone, centralized network/security/logging, warm standby, cross-region operations, formal control mappings, staffed on-call and change governance | Documented and modeled; not run continuously in personal AWS |

## Phased plan for one experienced engineer

Effort is a planning estimate for focused engineering time, not a promise. AWS work depends on account setup and selected region. All cloud phases require a budget estimate and teardown plan first.

| Phase | Deliverables and tasks | Dependencies | Validation / evidence | Effort | Exit condition / cost |
|---|---|---|---|---:|---|
| 1. Business workflow | Scope, actors, entry lifecycle, explicit non-goals | None | Reviewed workflow and data boundaries | 2–3 days | One workflow; no external payment rails; local cost zero |
| 2. Threat model | Data classes, abuse cases, IAM and audit plan | Phase 1 | Threat table, approved synthetic fixtures | 2–3 days | No real data/credentials in plan; local cost zero |
| 3. Transaction core | PostgreSQL schema/migrations, idempotency, outbox, correction record | Phase 1 | Unit/integration and replay evidence | 4–7 days | Correctness invariants hold locally; no cloud cost |
| 4. Local delivery | Container, Helm template, developer quickstart | Phase 3 | Rebuild and reproduce demo from clean checkout | 2–4 days | Local path works and is disposable; no cloud cost |
| 5. AWS guardrails | State bootstrap, budget, tags, IAM, VPC and network policy | Phase 2 | Plan review, policy output, resource inventory | 4–6 days | Human-reviewed plan and approved spend; charges begin only after apply |
| 6. EKS + database | Small EKS cluster, RDS PostgreSQL, KMS, Secrets Manager | Phase 5 | Connectivity, identity, failover and backup evidence | 5–8 days | Private DB, scoped service identity, explicit cost stop date |
| 7. Queue + GitOps | SQS/DLQ, publisher/consumer, GitHub Actions OIDC, Argo CD | Phases 3, 6 | Duplicate, retry, DLQ, promotion evidence | 5–8 days | No long-lived AWS credentials; reviewed promotion |
| 8. DevSecOps | SBOM, dependency/image scans, provenance, admission policy | Phase 7 | Workflow artifacts and rejection examples | 3–5 days | Blocking policies documented and evidenced |
| 9. Observability/SRE | Metrics, traces, SLO dashboards, runbooks, incident drill | Phases 6–8 | Dashboard, alert, postmortem evidence | 4–6 days | Business correctness visible beyond infrastructure health |
| 10. Recovery/resilience | Backup restore, queue replay, controlled fault experiments | Phase 9 | Measured RTO/RPO report and reconciliation | 4–7 days | No objective claimed without recorded exercise |
| 11. FinOps | Cost dashboards, teardown, orphan inventory, measured actuals | Phase 5 | Before/after estimate and residual resource list | 2–4 days | Teardown is repeatable; all retained charges understood |
| 12. Portfolio | README, diagrams, ADRs, demo, interview package | Earlier phases | Public-ready claims map to evidence | 2–3 days | Implemented/planned/simulated states are current |

Indicative total is about 5–9 focused weeks, depending on how much of the advanced tier is completed and how often infrastructure is deployed. Do not attempt every enterprise feature before transaction correctness and reproducibility are complete.

## Validation strategy and acceptance criteria

The following are acceptance criteria to implement and execute. They are **planned**; this starter does not include automated test files or recorded test runs. Keep a result ledger with commit, command, environment, timestamp, outcome, and artifact link. Never change a row to “passed” without evidence.

| Area / acceptance criterion | Test or check to add | Expected result | Evidence | Status |
|---|---|---|---|---|
| Same idempotency key + same body creates one entry | API integration test with concurrent/repeated requests | Same entry ID; exactly one entry, audit event, and outbox event | Test report and DB query | Planned |
| Same key + different body is rejected | API integration test | HTTP 409; original entry unchanged | Response capture and DB query | Planned |
| Invalid transition or invalid payload is rejected | Domain/API tests | No write and clear validation error | Test report | Planned |
| Entry, audit, outbox atomicity | Inject failure between writes | All commit or all roll back | Transaction test and DB state | Planned |
| Duplicate event has no duplicate business effect | Consumer replay test | One receipt/effect for event ID | Consumer test and receipt query | Planned |
| Publisher crash after broker send is safe | Fault-injection integration scenario | Duplicate send is harmless; one effect remains | Event trace and reconciliation report | Planned |
| Poison event is quarantined | Queue integration test | DLQ alarm and documented redrive path | DLQ record and operator evidence | Planned |
| Reconciliation detects missing receipt | Seed controlled discrepancy | Discrepancy is identified by event/entry ID | Reconciliation output | Planned |
| Infrastructure policy blocks unsafe change | Terraform policy fixture | Public DB / broad IAM / missing encryption is rejected | CI result | Planned |
| Image policy rejects noncompliant image | Admission/pipeline scenario | Unsigned or disallowed image is blocked | Admission event | Planned |
| Deployment rollback follows failed signal | Canary failure injection | Promotion halts and stable revision is restored | Argo history and alert timeline | Planned |
| Pod/node disruption preserves committed DB state | Isolated cluster fault test | Service resumes within measured objective; entry survives | Timestamped event and DB evidence | Planned |
| Backup restoration meets recovery objectives | Restore into isolated environment | Measured duration/data point recorded against target | Restore log and reconciliation report | Planned |
| Sensitive fields do not enter telemetry | Log/trace scan with canary markers | No prohibited marker in logs, traces, metrics, or AI prompt | Scan report | Planned |
| Audit evidence traces to change/operation | Evidence review | Change ID, actor, revision, and operation correlate | Evidence index | Planned |
| Cost safeguards and teardown behave | Deploy short-lived stack and tear down | Alerts arrive, resources absent or explicitly retained | Billing estimate, inventory, cleanup record | Planned |
| Rebuild is reproducible | Clean-machine walkthrough | Documented local workflow reaches demo state | Session capture and version list | Planned |

Test categories as the project grows: Terraform format/validation and policy tests; Kubernetes/Helm render checks; application/domain and integration tests; transaction replay tests; security and dependency scans; load tests; backup/restore tests; failover and chaos experiments; CI pipeline and teardown tests; cost-inventory checks. Planned criteria are not execution claims.

## 12-minute local demonstration

### Preconditions

- Python 3.12+, PowerShell, a clean checkout, and no production credentials.
- Use a new disposable database path under `work/`; never point to real servicing data.
- For the cloud extension only: approved account/region, reviewed current Pricing Calculator estimate, budget notification, bounded node count, and confirmed teardown operator. This repository does not provision it yet.

### Steps and expected evidence

1. **(1 min) State scope.** Show the disclaimer, workflow, and high-level diagram. Say the app is synthetic, local, and not a payment rail.
2. **(2 min) Start API and worker.** Run the README commands in two terminals. Expected: API listens on `localhost:8080`; worker stays idle until an outbox row exists.
3. **(2 min) Record an entry.** Submit a synthetic request with a fresh key. Expected: `201`, a generated `se_…` ID, and state `RECORDED`.
4. **(2 min) Retry safely.** Repeat exactly the same request and key. Expected: same ID and `idempotency_replayed: true`; change the amount with the same key and expect `409 IDEMPOTENCY_CONFLICT`.
5. **(1 min) Show event processing.** Run worker with `--once` or keep it running. Expected: one local receipt; explain the shared SQLite transaction is a simulator and the AWS queue delivery remains at least once.
6. **(1 min) Explain recovery and observability.** Show the planned SLO/DR objectives and label them unmeasured; point out how queue age and reconciliation expose business delay.
7. **(1 min) Explain security and cost.** Show data classes, human approval gates, and cleanup inventory. Do not expose account details or credentials.
8. **(2 min) Close on evidence gaps.** State that EKS, Terraform, SQS, CI/CD, alarms, restore tests, and performance results are planned/reference-only until evidenced.

### Local commands and cleanup

Start the API and worker as shown in the README. After the demonstration, stop both with `Ctrl+C`, then delete the disposable database file and its `-wal`/`-shm` companions under `work/`. For AWS, run reviewed teardown, wait for completion, and inventory the account for residual EBS, snapshots, NAT, load balancers, addresses, log groups, and S3 evidence before considering cleanup complete.

Prioritize the transaction flow, same-key retry, conflicting reuse, and replay explanation. Progressive delivery, policy rejection, backup restore, and AI recommendation are future demonstrations until built and evidenced.

