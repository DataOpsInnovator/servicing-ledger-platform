# Operations, security and recovery runbook — v2

**Purpose:** operational rehearsal with synthetic data only. Every AWS action requires an approved staging change; no production execution is implied.

## Day-2 checklist

- Check `/readyz` internally; inspect API errors and p95, pending and awaiting-consumer counts, oldest pending seconds, integrity errors and archive backlog. Shared DB metrics use max across replica scrapes. `/healthz` only tests process liveness; readiness tests schema access, not SQS or archive. Alertmanager/SNS routing must be independently tested.
- Check worker deployments, failed archive Jobs and CloudWatch DLQ/queue age/RDS CPU alarms. Monitor RDS connection count, storage and failover events, node pressure, certificate expiration and secret rotation (additional site-specific alarms). Structured logs exclude tokens, raw bodies and raw loan IDs; do not enable debug logs with credentials. Restrict audit data and pseudonymous identifiers.
- Review ECR scan and dependency results continuously. Rotate workload credentials with controlled restart, maintain updated RDS CA, verify issuer/key rotation. No real PII; preserve access and change evidence.

## Incident matrix

| Signal | Immediate action | Recovery and verification |
|---|---|---|
| High 5xx/readiness failure | Stop rollout; check RDS, schema and network/TLS | Recover DB connectivity; retry with original key; compare entries and audit |
| Outbox age grows | Check publisher logs, DB locks, role/queue access and SQS quotas | Restore dependency; backlog drains; monitor no missing receipts |
| DLQ nonempty | Quarantine incident; read safely via authorized role, determine poison/retention failure | Correct cause; approved redrive or audited requeue; verify DB receipt and no duplicate |
| Reconciliation discrepancy | Freeze affected synthetic workflow; preserve evidence and escalate | Independent comparison of entry/audit/outbox/receipt; fix through approved migration/compensating record, not deletion |
| Audit archive lag/mismatch | Preserve DB/snapshots; inspect archive Job/permissions/object checksum | Resolve without overwriting locked versions; compare immutable bytes and receipt |
| Incorrect entry | Operator confirms reason; full reversal with new key | Confirm original unchanged, reversal linked and net amount expected; new corrected entry only under separate key |
| Leaked access credential | Revoke/rotate through provider or Secrets Manager + DB role; restart affected pod | Verify old credential rejected and new connection; incident documentation |

### Requeue and poison messages

SQS redrive is not automatic recovery of business correctness. Inspect the DB outbox row and queue/DLQ metadata using approved read-only access; don't log event payloads outside approved incident workspace. If a published event is missing/expired and still unhandled, schema-owner maintenance command can clear its publication marker and append a requeue audit record:

```bash
# On authorized maintenance runner using correct DB settings and approved incident:
python -m app.admin requeue evt_REPLACE_WITH_32_HEX --incident INC-123456 --confirm-investigated
```

It refuses handled, quarantined and unpublished rows. The publisher resends at least once and consumer deduplicates. Do not use for malformed persisted payloads; retain evidence and escalate to product/control owner. Reconcile source and audit receipts after redrive. Manual SQL mutation of entries/audit is prohibited. No general DLQ repair UI or auto-remediation is included.

## Recovery exercises

### Local verified backup

`python -m scripts.local_acceptance` creates and drains 200 entries, backs up and validates SQLite restore. Manual: stop writes if needed for comparable snapshot; `python -m app.admin backup /safe/unique/backup.db`; set `SERVICING_DB_PATH` to restored copy in isolated environment; `python -m app.admin reconcile`. Backup refuses overwriting existing destination. SQLite is not a cloud data store.

### PostgreSQL logical restore (CI, not yet executed)

The CI PostgreSQL job runs integration tests, `pg_dump -Fc --no-owner --no-acl`, `pg_restore --exit-on-error` into distinct database and `python -m scripts.verify_postgres_restore` against quiesced source and restored database. Compare fingerprints of entries, audit, outbox, consumer receipts and archive receipts. CI DSNs are disposable test-only credentials; for real operation use protected environment/PGPASSFILE and do not pass live credentials as command-line arguments. Script accepts `SOURCE_DATABASE_URL` and `RESTORED_DATABASE_URL` environment variables. Ownership/grants must be restored and checked independently; a data match does not prove permissions, encryption or PITR readiness.

### RDS failover exercise (requires approved staging and costs)

1. Obtain change ticket, alert responders, record planned impact, healthy baseline and exact start timestamp. Confirm RDS Multi-AZ status and backup retention, test data only. Run cloud smoke baseline. Keep synthetic clients retrying same keys with bounded backoff.
2. Via RDS console or approved CLI action **Reboot with failover** for the isolated staging instance; do not use real business production. Record observed downtime and connection errors. Wait for instance `available` and API readiness.
3. Verify same-key retries return prior ID, no duplicate, reconciliation clean, queue drained and audit archive catches up. Record measured availability interruption and failures; compare proposed SLO only after measurement.
4. Failover exercise does not establish PITR. Use separate recovery drill below.

### RDS point-in-time restore exercise (requires approved staging and costs)

1. Record reference journal entries and committed timestamps, last recoverable time, intended recovery point (UTC), and source identifier. Quiesce source for exact comparison or establish a known point-in-time sentinel. Ensure recovery target has separate identifier/SG and no live client routing. Confirm retention, budget and rollback plan.
2. In AWS RDS console select source → Restore to point in time → choose approved UTC timestamp and new instance identifier in isolated DB subnets with no public access, encryption, correct parameter group and security group. Review and authorize charges before restoring. Do not overwrite source.
3. Use approved admin runner with TLS `verify-full`; verify schema version, table counts, known pre-recovery sentinel and absence of post-recovery sentinel. Compare full fingerprints only if quiesced matching snapshot. Validate role grants and trigger behavior. Restore does not restore queue state; keep old publisher/consumer off restored DB until compare published/unhandled and archive receipts, and determine replays with controls. Never point restored instance at the live queue by default.
4. Measure RTO from declaration to verified readiness (not just RDS `available`), RPO from latest intended committed entry to last recovered commit; record errors, missing rows, recovery evidence and approvals. Proposed 60m RTO/15m RPO are not validated. If switching staging traffic is approved, rotate role DSNs to new endpoint and restart, retaining original source for rollback. Validate no duplicate and audit completeness; collect results. Clean up approved disposable restore resources after retention review.

### Recovery evidence template

| Field | Record |
|---|---|
| Change/incident ID, owner, environment | |
| Source/target IDs and timestamp UTC | |
| Recovery method, approvals | |
| Declared / DB available / acceptance time | |
| Latest intended vs recovered commit; observed RPO | |
| Observed RTO; test cases, counts, fingerprints | |
| Permissions, audit and queue reconciliation | |
| Exceptions, rollback, sign-off | |

## Go-live conditions (not satisfied by this archive)

Require independent security/control review, validated AWS Terraform plan and apply, current vulnerability scan, pinned build inputs, admission-time signature enforcement, tested IAM/DB privileges, real OIDC, secure ingress/egress, logging retention, scalable DB connections, external financial reconciliation and approval model, verified alerting and successful load/failover/PITR exercises. A staging run is not production certification. Preserve audit retention, backup and change evidence per approved organization policy.
