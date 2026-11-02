# Security, controls, SRE, recovery, and cost

## Financial data and transaction integrity

The simulator accepts only synthetic `SYN-` loan references and integer cents in USD. It does not calculate balances, authorize disbursements, or call a payment rail. In an enterprise implementation, the system of record would own the actual servicing state and correction policy.

| Data class | Examples | Handling |
|---|---|---|
| Public | Architecture docs and source code | Review before publishing; no secrets |
| Internal operational metadata | Deployment revision, bounded service name, queue age | Access controlled; retain to the stated operational purpose |
| Confidential synthetic records | Synthetic entry ID, loan reference, amount, event history | Encrypt in transit/at rest; redact from routine logs; keep synthetic-only |
| Sensitive customer/financial data | Real names, account numbers, credentials, payment data | Prohibited in portfolio fixtures, telemetry, prompts, demos, and screenshots |
| Secrets and cryptographic material | DB credentials, signing keys, KMS key material | Managed secret/key services; never commit or log; short-lived access |

### Correctness rules

1. Canonicalize and validate the request before opening a write transaction.
2. Enforce a unique idempotency key at the database layer. Same key/same digest returns the original record; same key/different digest is a conflict.
3. Commit entry, audit event, and outbox row atomically. An acknowledged entry therefore has a durable event to publish in the same database transaction.
4. Use optimistic versions or row-level locking for later state transitions. Define allowed transitions explicitly; never permit direct balance mutation.
5. Give each event an immutable ID, schema version, aggregate/entry ID, timestamp, and correlation ID. Persist a consumer receipt with the downstream effect in one transaction.
6. Expect duplicate delivery. SQS Standard provides at-least-once delivery and advises idempotent consumers; message-level deduplication alone is not a substitute for database-level business-effect deduplication. See [SQS at-least-once delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html).
7. Use a DLQ for repeatedly failing events, investigate the reason, then replay with the original event ID or issue a controlled compensating/correction record. Never delete or silently rewrite the original audit history.
8. Reconcile accepted entries against outbox and consumer receipts. Report accepted, pending, failed, and corrected counts and identify gaps by synthetic IDs.

The local Python implementation demonstrates rules 2 and 3 with SQLite and a local worker. The AWS/PostgreSQL/SQS adapter and full correction workflow are future work. Infrastructure availability and business correctness are separate: a `200` or a healthy pod does not prove that an entry was recorded once or reconciled.

## Threat model and DevSecOps

| Threat / failure | Example consequence | Controls and evidence planned |
|---|---|---|
| Spoofed client or replay | Unauthorized synthetic entry or duplicate effect | TLS, authenticated workload path in AWS, idempotency constraint, rate limits, authn/z tests |
| Excess privilege | Workload reads unrelated secrets or alters infrastructure | Per-workload identity, scoped IAM, namespace RBAC, protected plan/apply separation |
| Public exposure | Database, cluster API, or admin surface reachable from internet | Isolated data subnets, no public DB IP, allowlisted cluster API, private nodes, reviewed ingress |
| Secret or financial data leak | Sensitive values in Git, image, logs, traces, or AI prompts | Secret scanning, synthetic fixtures, payload redaction, minimal structured fields, retention review |
| Malicious dependency/image | Code execution or compromised release | Pinned dependencies/actions, SBOM, dependency/image scans, provenance/signature verification, admission policy |
| Tampered audit evidence | Dispute cannot be reconstructed | Append-only application events, CloudTrail, restricted S3 retention, separate write/read roles, integrity checks |
| Failed or partial deploy | Inconsistent versions or unavailable API | Immutable image digest, staged rollout, readiness checks, abort/rollback, change record |
| Ransomware or operator error | Destroyed data or infrastructure | Protected backups, separate permissions/account, restore rehearsal, deletion gates |
| Queue poison/backlog | Delayed servicing work or duplicate replay | DLQ, oldest-age alarm, idempotent consumer, operator runbook, reconciliation before replay |
| Regional outage | Loss of service and delayed entries | Backup copy and restore runbook; warm standby only if business-approved objectives justify cost |

CI should reject formatting/validation failures, vulnerable dependencies above policy, exposed secrets, unapproved Terraform modules, unsigned images, missing ownership metadata, and prohibited public resources. Exceptions need an owner, rationale, expiration, and approval. Dependency updates are reviewed and pinned; no build downloads execute with AWS deployment credentials.

## Auditability and regulatory-control alignment

This repository demonstrates control design and evidence generation; it is not a compliance assessment or certification. Do not claim PCI DSS, SOC 2, SOX, or regulatory compliance from the project alone.

| Control objective | Portfolio evidence to capture | Limitation |
|---|---|---|
| Change authorization and separation of duties | PR approvals, workflow identity, Terraform plan hash, apply record | A one-person project cannot demonstrate enterprise segregation of duties fully |
| Least privilege and identity | IAM policy review, OIDC role session, EKS access entry, service identity mapping | Must be assessed against real organization and account boundaries |
| Data protection | KMS configuration, encrypted database/queue, TLS policy, secret-rotation record | Does not prove policy compliance or key governance at an institution |
| Configuration baseline | Terraform plan, policy checks, drift report, tagged inventory | Evidence only covers resources managed and monitored by the project |
| Operational resilience | Backup/restore logs, recovery timeline, reconciliation report, incident review | No recovery objective is met until tested and measured |
| Audit integrity | CloudTrail trail configuration, restricted evidence bucket, retention policy, checksum manifest | Application-level append-only is not tamper-proof storage by itself |

Control mapping is illustrative and should be reviewed by compliance/legal specialists before any regulated production use. Records retention and deletion periods are intentionally unset pending that review.

## Observability and proposed SLOs

Four telemetry layers: (1) infrastructure and Kubernetes capacity; (2) API and worker behavior; (3) synthetic user-visible success and latency; (4) business correctness such as duplicate conflicts, pending events, DLQ age, and reconciliation gaps. Propagate correlation ID and event ID. Do not use loan references, request payloads, idempotency keys, or amounts as metric labels. Redact logs and traces. Keep AWS API audit events separate from application business events.

| Proposed SLO (not measured) | Measurement window/method | Initial target | Alert condition and rationale |
|---|---|---|---|
| API availability | 30-day rolling: valid requests receiving a durable `RECORDED` response / valid requests | 99.5% | 5xx/timeout burn-rate alert; excludes invalid client requests |
| API latency | 30-day rolling p95 at API edge for valid requests | < 500 ms | Short-window p95 > 1 s or sustained monthly budget burn; final target needs workload benchmark |
| Event completion | Accepted entries with consumer receipt within 5 minutes / accepted entries | 99% | Oldest pending event > 5 min, DLQ nonempty, or reconciliation gap; measures business flow, not just pod health |

Error budget and escalation: the service owner reviews monthly SLO burn and incidents; a rapid burn pauses risky releases, while a sustained breach prioritizes reliability work. Initial thresholds are proposals. The project has no telemetry backend wired up yet, so these are not observed results.

Dashboard hierarchy: environment/cluster → API and worker service health → synthetic transaction lifecycle → audit/reconciliation and queue/DLQ → cost and recovery evidence. Runbooks link alerts to diagnosis, containment, and evidence capture. Incident severity is based on customer/business impact in a production setting; this portfolio uses synthetic scenarios only.

For the portfolio, critical alert routing is a documented primary-operator notification path and is not configured in this scaffold. A production service should route actionable pages to the owning on-call rotation, use a backup escalation path, define incident commander/communications roles, and review post-incident actions. Non-actionable alerts stay in dashboards or ticket queues rather than paging.

## High availability and disaster recovery

### Strategy and targets

Portfolio deployment strategy: one primary AWS region, workloads spread across at least two AZs, RDS Multi-AZ where the budget permits, protected backups, and **backup-and-restore for regional disaster recovery**. Proposed region-loss objective is 8-hour RTO and 24-hour RPO, subject to actual backup schedule, restore duration, and reconciliation tests. For an RDS Multi-AZ DB instance deployment, AWS documents synchronous replication to a standby in another AZ and automatic failover support; that protects an AZ/instance failure within the region, not a regional outage. See [RDS Multi-AZ behavior](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html) and [AWS RDS DR guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/dr-standard-edition-amazon-rds/sites-strategies.html).

| Failure domain | Proposed objective | Data caveat |
|---|---|---|
| Pod/node failure | API resumes within 15 minutes; no loss of committed DB data | Objective requires a live cluster and health checks |
| AZ/DB instance failure | Resume writes within 30 minutes; target zero loss for acknowledged commits in synchronous Multi-AZ | Must validate real failover and caller retry behavior |
| Region failure | Restore service within 8 hours; up to 24 hours of records at risk under backup-and-restore assumption | Cross-region backup cadence and restore point determine actual RPO |
| Queue backlog | Resume processing and drain within 2 hours after dependencies recover | Oldest-event age and event IDs govern safe replay |

An enterprise reference may choose warm standby for a tighter approved objective, but it adds continuous database, networking, compute, and operational cost. Cross-region asynchronous replication has nonzero lag; transaction outcomes near failover must be reconciled before replay. Never claim exactly-once processing or zero RPO across regions.

RTO applies to application access; RPO applies to durable accepted records. For region loss, the database backup point determines the record recovery point, while the service objective is 8 hours to restore. Queued work has a separate drain objective of 2 hours after dependencies return; if a queue in the lost region is unavailable, restored outbox rows are reconciled and republished with their original event IDs. A queue's transport durability does not remove the need to reconcile publication acknowledgments and consumer receipts.

### Recovery runbook

1. Trigger when health evidence confirms a regional outage or primary data plane cannot recover inside the approved decision window.
2. The incident commander declares severity and receives business/operations authorization before cutover.
3. Confirm source-region state, latest recoverable backup timestamp, queue/DLQ status, and restore permissions. Preserve evidence before changing routing.
4. Restore database and infrastructure from known versioned artifacts into the recovery region; apply only reviewed Terraform and manifests.
5. Validate encryption, identities, schema version, connectivity, and application health. Keep external payment/servicing integrations disabled.
6. Compare synthetic entry IDs, audit records, outbox rows, and consumer receipts across recovered data. Identify the recovery point and any ambiguous requests.
7. Replay only missing events using original event IDs; unique consumer receipts prevent repeating completed effects. Quarantine unknown outcomes for operator review.
8. Verify business workflow, queue age, error rate, and dashboard signals. Record measured RTO/RPO and evidence hashes.
9. Obtain authorization for controlled DNS/endpoint cutover; notify project stakeholders with actual status and known data gap.
10. Fail back only after source recovery, replication/reconciliation, and a separately reviewed change. Retain incident evidence and conduct a postmortem.

## Controlled resilience experiments

All experiments are synthetic and disposable. Begin locally or in a time-limited dev environment. Every cloud experiment needs an owner, change ticket/PR, abort condition, budget gate, and cleanup verification. No production or real financial system is in scope.

| Experiment | Hypothesis / signals | Safety and abort | Success evidence |
|---|---|---|---|
| Kill API pod | New pod serves; committed entries remain readable | One demo replica only; stop if DB health degrades | Recovery time and entry ID retained |
| Duplicate request | Same key/body produces one entry | Synthetic key and isolated database | One entry and one outbox event |
| Duplicate event | Receipt uniqueness prevents second consumer effect | Replay one known synthetic event | One receipt, stable state, audit trail |
| Database unavailable | API fails closed without false success | Local fault injection or isolated dev DB | 503/no new entry, recovery and retry evidence |
| Queue delay/poison message | Backlog and DLQ alarms identify delay | Bound message count; no external targets | Alarm, DLQ diagnosis, controlled replay |
| Failed rollout | Readiness or business signal blocks promotion | Canary only; preapproved rollback | Rollback revision and event correctness evidence |
| Backup restore | Restore point and reconciliation satisfy proposed target | Restore to isolated destination; never overwrite primary | Restore duration, recovered IDs, measured RPO |
| Regional recovery | Runbook restores only controlled dependencies | Tabletop first; no automatic DNS failover | Approvals, timeline, gaps, evidence inventory |

## FinOps and personal-account safeguards

### Cost envelope

Region assumption: `us-east-1`; all figures below are **planning envelopes**, not quotes or measured bills. Rebuild each estimate in the [AWS Pricing Calculator](https://calculator.aws/) immediately before deployment, including OS/license choices, AZ count, transfer, backups, log retention, and account-specific discounts. The [EKS pricing page](https://aws.amazon.com/eks/pricing/) currently lists `$0.10` per cluster-hour for standard Kubernetes version support and `$0.60` per hour for extended support; worker EC2, storage, public IPv4, transfer, and managed dependencies are separate.

| Profile | Explicit assumption | Indicative envelope |
|---|---|---|
| Low-cost portfolio demo | One EKS cluster; one small on-demand node; one NAT; single-AZ small PostgreSQL for disposable data; one ALB; 8-hour demo window, then teardown | Roughly `$8–$25` per 8-hour window; full-month idle cluster with a live NAT/DB can exceed `$150–$300/month` |
| Production-style reference | Three-AZ EKS worker capacity, per-AZ NAT, Multi-AZ PostgreSQL, ALB/WAF, SQS/DLQ, backup copies, retained logs, monitoring | Roughly `$700–$1,800/month` before material traffic, support, discounts, or high-volume telemetry; calculator required |

These wide ranges reflect changing instance/storage choice, AZ topology, telemetry, and data transfer; do not present them as AWS quotes. Five likely cost drivers: EKS control plane and EC2 nodes, NAT gateways/data processing, Multi-AZ database, load balancer/public IPv4, and logs/metrics/retention. Cost-versus-resilience: per-AZ NAT and Multi-AZ database increase cost but reduce single-AZ dependencies; a disposable workshop may use one NAT/single-AZ DB only if the failure limitation is explicit.

### Controls

- Set an AWS Budget with low warning thresholds and cost-anomaly notifications before creating resources. AWS notes budget notifications may be delayed relative to usage, so they cannot impose a hard spending cap: [AWS Budgets guidance](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html).
- Use an explicit deployment gate, short-lived environment schedule, max node count, service quotas, required tags, and teardown workflow. At teardown, inventory EKS, EC2, EBS, RDS snapshots, NAT gateways, load balancers, public IPv4/EIPs, CloudWatch log groups, S3 artifacts, and backup recovery points.
- Never deploy the production reference continuously. Keep a documented list of charges that survive workload deletion; require human approval for destructive teardown and verify the remaining-resource inventory afterward.
- Use Graviton where images and dependencies support it; Spot only for interruptible workers; Karpenter consolidation only after a cost/reliability rehearsal; lifecycle old artifacts and bound log retention. Savings Plans/Reserved Instances are out of scope for a variable portfolio schedule.
- Estimate versus actual cost is recorded separately by month, environment, and resource tag; no savings claim is made without a reproducible comparison.

## AI-assisted operations (advisory only)

**Example (hypothetical):** `OldestPendingEventAge` crosses 5 minutes shortly after deployment `rev-abc123`; the DLQ contains one synthetic event and the database health alarm is clear. The assistant reports that deployment timing is correlated but does not prove causality, cites the queue-age alarm and recovery procedure above, recommends pausing promotion and comparing event IDs against outbox rows/consumer receipts, and asks the operator to authorize any replay. It does not redrive the queue, roll back the deployment, or change infrastructure itself.

Proposed feature: summarize a synthetic queue-backlog incident from approved alarm metadata, runbooks, architecture records, and change history. The assistant may recommend inspecting the DLQ, recent deployment, or database health and cite the exact alarm/runbook evidence. It must state uncertainty and refuse when evidence or authorization is insufficient.

Never send financial records, customer identifiers, secrets, payment data, or raw request payloads to a model. Redact at ingestion; restrict source access; preserve prompt/output audit metadata; use a deterministic runbook fallback. A human approves remediation. The assistant cannot replay events, alter balances, approve a payment, execute Terraform, change traffic, or perform destructive actions. Tests for hallucination, prompt injection, stale runbooks, authorization failure, and unsafe action recommendations are future work. Conventional alerting and automation remain responsible for deterministic operations.

