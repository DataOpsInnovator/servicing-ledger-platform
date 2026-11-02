# Portfolio presentation and interview preparation

## GitHub repository presentation

**Repository name:** `servicing-ledger-platform`  
**Subtitle:** Synthetic, auditable loan-servicing entry workflow with idempotency, outbox delivery, AWS platform design, and explicit recovery/cost boundaries.

The repository is an independent portfolio project. It does not represent a deployed financial institution platform, a bank/lender client, or the candidate's professional production work. It does not make real payments or store real customer data.

Suggested GitHub topics: `aws`, `platform-engineering`, `eks`, `terraform`, `gitops`, `financial-services`, `loan-servicing`, `transaction-integrity`, `sre`, `devsecops`.

Definition of ready for a public release: reproducible local run; automated checks with attached evidence; no secrets or real data; current diagrams; source references; cost warning; ownership/approval rules; recovery runbook; status labels for implemented, validated, simulated, and documented capabilities. This initial repository is **not yet at that release bar** because execution evidence and automated checks have not been added.

Release milestones:

1. `0.1.0` — local API/outbox simulator and reference docs.
2. `0.2.0` — persistence migration, application checks, and reproducible local container evidence.
3. `0.3.0` — isolated AWS development stack and teardown record.
4. `0.4.0` — SQS, GitOps, security pipeline, dashboards, and measured recovery.
5. `1.0.0` — only after acceptance evidence is complete and project status is independently reviewed.

## LinkedIn Featured project entry

**Servicing Ledger Platform — Synthetic Loan-Servicing Reliability Reference**

Designed an independent portfolio project around a narrow loan-servicing workflow: safely recording synthetic servicing entries and processing downstream events without duplicating business effects. The repository includes a local Python API and outbox-consumer simulator, plus an AWS reference architecture for EKS, PostgreSQL, SQS, Terraform, GitOps, auditability, and recovery.

Key decisions include a relational source of truth for atomic entry/audit/outbox writes, durable idempotency keys, consumer-side duplicate handling, and backup-and-restore as the cost-conscious portfolio recovery strategy. The project uses synthetic data only and does not initiate or settle payments.

Cloud deployment, automated test evidence, recovery measurements, and performance results are not yet claimed. The architecture and validation plan distinguish implemented code from future AWS work.

Repository: `<add public GitHub URL after publishing>`

## Interview narrative

### 30-second summary

“I designed a portfolio platform around one loan-servicing problem: recording a synthetic servicing entry safely when clients retry and downstream processing is asynchronous. The local implementation writes the entry, audit event, and outbox record together and uses a unique idempotency key; the worker records a unique receipt so replay is safe. The AWS reference uses PostgreSQL, SQS, EKS, Terraform, and GitOps, but I label those pieces as planned until they're deployed and measured. It never processes real payments or customer data.”

### 90-second project pitch

“The business scenario is an internal servicing channel that needs a trustworthy record of a servicing entry even when callers retry or downstream consumers are slow. A generic API returning 200 would not be enough: the entry could exist without an event, or an event could be delivered twice. I made the core write a single database transaction containing the entry, the idempotency key and request digest, an audit event, and an outbox row. The publisher/consumer design assumes at-least-once delivery, so consumer receipts are unique by event ID and are committed with their business effect.

“The local code demonstrates the state transition with synthetic data in SQLite. The AWS target moves to PostgreSQL, SQS, and EKS, with Terraform and Argo CD controlling infrastructure and workloads. The MVP is intentionally single-region and backup-and-restore for cost; the enterprise reference can move to warm standby only if an approved recovery objective justifies the operational cost. I separate API health from business correctness with queue age and reconciliation indicators. No AWS deployment, recovery objective, throughput, or compliance status is claimed until reproduced. The work is useful to me because it connects cloud platform decisions to financial transaction integrity and operational evidence rather than just provisioning services.”

### Five-minute architecture walkthrough

1. Explain the workflow and boundary: synthetic servicing entry only, no payment execution or balance calculation.
2. Show the idempotency contract and conflict behavior; explain why the key and canonical request digest are database-enforced.
3. Walk through atomic entry/audit/outbox commit, then the outbox publisher and at-least-once queue boundary.
4. Explain unique consumer receipts, DLQ handling, and reconciliation; distinguish transport success from business completion.
5. Show one-region AWS target: EKS private workloads, PostgreSQL in isolated subnets, SQS, KMS/secrets, CloudTrail/CloudWatch, and GitOps.
6. Explain EKS versus ECS and why the project chooses learning/platform value while acknowledging additional burden.
7. Discuss backup-and-restore for the portfolio and warm standby only as an enterprise option; targets remain unvalidated until exercises are measured.
8. Close on deployment approval, cost teardown, synthetic-only telemetry, and the status table showing what is implemented vs planned.

## Senior-level interview questions and answer outlines

1. **Why relational storage instead of DynamoDB?**  
   The core command needs one atomic boundary across the servicing entry, idempotency key, audit row, and outbox event. PostgreSQL expresses that transaction and uniqueness constraint directly. DynamoDB could work with conditional writes and transactions if access patterns and limits fit, but it would require a different modeling and operational argument. The portfolio choice is not a claim that PostgreSQL is universally superior.

2. **How do you make the request idempotent?**  
   The caller supplies a stable key. The service canonicalizes the validated payload, hashes it, and stores key plus digest under a unique constraint in the same transaction as the entry. Same key and same digest returns the original result; same key and different digest is a conflict. The key retention period must exceed the retry/replay horizon and be reviewed as a data-retention decision.

3. **Does SQS give you exactly-once business processing?**  
   No. Standard queues can redeliver. The producer uses an outbox to avoid losing the event between a committed database change and publish; a publisher crash can still create duplicate messages. The consumer stores an event receipt and business effect in one transaction. That gives an idempotent effect at the consumer boundary, not exactly-once transport across the distributed system.

4. **Why EKS for one small API?**  
   ECS would be a simpler and likely cheaper host. I use EKS in the reference because the portfolio is meant to demonstrate a reusable platform path and the candidate profile includes Kubernetes. The trade is cluster, node, upgrade, add-on, policy, and on-call burden; I keep the live MVP short-lived and would choose ECS if the platform demonstration were not a requirement.

5. **How do you avoid publishing an event before the record commits?**  
   The event is first written to an outbox row in the same relational transaction as the record. A separate publisher sends committed outbox rows. The publisher marks a row after broker acknowledgment, so crash windows can create duplicate sends but not a missing committed intent; idempotent consumption handles duplicate sends.

6. **What happens on database failover?**  
   API connections can fail during the transition and must reconnect with bounded retry/backoff. The caller may not know whether a request committed, so it retries with the same idempotency key. The database uniqueness constraint resolves the uncertainty. Failover time and data behavior must be observed in an isolated exercise before claiming a target.

7. **How do you handle a DLQ event?**  
   Alert on DLQ count and oldest-message age, capture event ID and error class without sensitive payloads, and compare it with the outbox and consumer receipt. Correct the root cause, then approve a bounded redrive using the same event ID. For a bad business event, append a correction record rather than editing history.

8. **How do you prove a request was processed correctly?**  
   Trace request ID to entry ID, audit event, outbox event, consumer receipt, and reconciliation result. API health and a 2xx are insufficient. Metrics should count accepted/rejected entries, duplicate conflicts, processing age, DLQ depth, and discrepancy rates using bounded nonsensitive labels.

9. **What are the recovery objectives?**  
   The portfolio proposal is 8-hour region-loss RTO and 24-hour RPO under backup-and-restore; these are targets, not results. Within-region Multi-AZ is a separate failure domain. Actual recovery requires restoring into an isolated region, reconciling entry/event IDs, measuring time and recovery point, and validating caller retry behavior.

10. **How is infrastructure change controlled?**  
    Pull requests run formatting, validation, policy/security checks, and produce a saved Terraform plan. A reviewer approves the plan; apply uses a short-lived OIDC role with narrower permissions than plan. Argo CD syncs a reviewed commit. Destructive or production-equivalent changes require a human approval and an evidence record.

11. **How do you stop an AWS bill from running away?**  
    A current calculator estimate and budget alerts come before deployment, but alerts can lag and are not a hard cap. I also gate deployment, bound node count, time-box the environment, tag every resource, schedule teardown, and inventory residual DB snapshots, NAT, load balancers, addresses, and logs.

12. **What does the compliance mapping mean?**  
    It maps design objectives to evidence types such as approved changes, IAM policy, encryption settings, and recovery artifacts. It does not demonstrate formal compliance. A real regulated deployment needs control owners, scope, evidence retention, independent assessment, and legal/compliance review.

13. **How do you secure Terraform state?**  
    Put it in a dedicated versioned, encrypted, private S3 bucket with a native lock file and narrowly scoped role access. Separate environment keys, protect the bootstrap path, do not commit state or plans, and treat state reads as sensitive. Use reviewed migrations/imports and recover from versions rather than manually editing state.

14. **Why not active-active across regions?**  
    It complicates ordering, idempotency, conflict resolution, and authoritative ownership while adding continuous cost. The initial scope does not justify it. I would revisit only if business-approved objectives and measured regional risk demand the additional design and operational burden.

15. **What has actually been implemented?**  
    The repository includes a standard-library local API, SQLite transaction/outbox simulator, local duplicate-safe receipt worker, starter Helm demo, and design documents. The current scaffold has not been validated by recorded automated test runs; AWS infrastructure, SQS integration, GitOps, dashboards, restore measurements, and benchmarks remain planned or reference-only.

## Stretch goals, ranked

| Rank / enhancement | Portfolio value | Complexity / burden / cost | Prerequisites and completion evidence |
|---|---|---|---|
| 1. PostgreSQL + SQS + transactional outbox | Very high: validates distributed transaction boundary | Medium / medium / medium | Schema migrations, integration environment; duplicate/crash-window evidence |
| 2. OIDC CI, signed images, admission verification | Very high: supply-chain and change controls | Medium / medium / low-medium | Protected repo and registry; rejected-image evidence and provenance |
| 3. Backup restore and reconciliation game day | Very high: operational maturity | Medium / medium / medium | Backups and isolated restore account; measured RTO/RPO report |
| 4. Platform template and scorecard | High: developer platform proof | Medium / medium / low | Multiple template consumers or services; reproducibility and guardrail results |
| 5. Warm standby recovery orchestration | High when objectives require it | High / high / high | Baseline restore evidence and business-approved RTO/RPO; controlled failover record |
| 6. Backstage service catalog | Moderate until many services exist | Medium / high / medium | Ownership metadata and multiple teams; catalog workflow evidence |
| 7. Cell-based isolation | High at scale, low for one service | Very high / high / high | Workload/tenant isolation requirements; failure-containment demonstration |
| 8. AI incident summarizer | Moderate if evidence grounded | Medium / medium / variable | Curated runbooks, redaction, authorization; citation, refusal, and safety evaluations |

Service mesh, Crossplane, SPIFFE/SPIRE, and eBPF are deferred until a concrete identity, policy, or telemetry requirement warrants their operating overhead.

## Final assessment

The strongest project is a narrow, auditable loan-servicing entry workflow, not an oversized bank platform. It demonstrates transaction correctness, change control, platform defaults, SRE signals, recovery thinking, and cost judgment. The minimum valuable scope is a complete local workflow with database migrations, idempotency and replay checks, synthetic data, readable architecture decisions, and honest evidence. Highest-value advanced work is PostgreSQL/SQS integration, short-lived OIDC delivery, and a measured restore/reconciliation exercise.

Main limits: a local SQLite simulator is not a production database; the AWS reference is not deployed; proposed SLO/RTO/RPO values are unmeasured; control mappings are not compliance; no business impact or cost savings are claimed. A reviewer may challenge EKS overhead, the weak portfolio region-loss objective, or missing test evidence. The honest responses are to show the alternatives and trade-offs, explain the incremental roadmap, and update claims only after reproducible evidence.

Target roles supported by completed and evidenced work may include Senior Cloud Platform Engineer, Staff Platform Engineer, Senior DevOps Engineer, Senior SRE, AWS Solutions Architect, Financial Services Cloud Infrastructure Engineer, and Platform Security/DevSecOps Engineer. The repository supports those conversations only to the extent each capability is actually implemented and demonstrated.

