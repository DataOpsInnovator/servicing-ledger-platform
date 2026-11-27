# Local deployment and operations runbook

> **Historical v1.0 reference.** Preserved for design and portfolio context. For current implementation, see [v2 architecture](architecture-v2.md) and the root README. Statements about unimplemented PostgreSQL/SQS/reversals or old test counts describe v1 only.


## Runtime configuration

| Variable | Default | Purpose |
|---|---|---|
| SERVICING_DB_PATH | work/servicing.db | SQLite database location |
| SERVICING_HOST | 127.0.0.1 | API bind host; container sets 0.0.0.0 |
| SERVICING_PORT | 8080 | API port |
| SERVICING_WRITER_TOKEN | none | Writer/read role, minimum 32 characters |
| SERVICING_OPERATOR_TOKEN | none | Operator/read role, distinct minimum 32 characters |

Generate secrets independently, use restricted file permissions, rotate by restarting the service with new values. These local tokens must be replaced by managed identity for enterprise use. Do not put tokens in logs, URLs, or version control. Avoid public ingress; TLS, rate limits and enterprise identity are not implemented at this boundary.

## Local or container operations

1. Run the tests and smoke command from README. For Compose, create `.env` from the example and run `docker compose up --build`.
2. Confirm `/readyz` returns 200. Check API and worker logs (`docker compose logs api worker` if containerized).
3. Create a synthetic entry, run a worker batch, and confirm operator reconciliation. Pending events should drain; quarantine or discrepancy counts should remain zero.
4. Stop with `Ctrl+C` or `docker compose down`. Keep the volume unless intentional deletion is approved.

## Kubernetes demonstration (unexecuted)

Build and load/push the image into an isolated test cluster. Create a namespace and an existing Secret with keys `writer-token` and `operator-token` using your approved secret mechanism. Do not commit secret manifests. Example deployment, after the image and secret are available:

```bash
helm lint deploy/helm/servicing-ledger --set auth.existingSecret=ledger-auth
helm template ledger deploy/helm/servicing-ledger --set auth.existingSecret=ledger-auth
helm upgrade --install ledger deploy/helm/servicing-ledger -n ledger-demo \
  --set auth.existingSecret=ledger-auth --set image.repository=servicing-ledger-demo --set image.tag=local
kubectl -n ledger-demo rollout status deployment/ledger
kubectl -n ledger-demo port-forward service/ledger 8080:8080
```

Default `emptyDir` is erased when a pod is removed. Set `storage.existingClaim` to a compatible pre-created single-writer PVC to retain data across pod replacement. Use storage supporting SQLite locking; never scale this chart to multiple pods. Back up before an upgrade. Helm rollback does not roll back a database migration; restore a compatible backup offline if necessary. No cloud infrastructure is provisioned.

## Incident triage

| Signal | Action |
|---|---|
| Readiness fails | Check storage path, permissions, schema version and capacity; verify migration before restarting |
| Repeated storage failures | Preserve database; inspect disk and lock contention; avoid blind retry loops |
| Pending grows | Check worker process and logs; run `python -m app.outbox_worker --once` after correcting failure |
| Quarantine > 0 | Preserve event evidence, investigate schema/envelope mismatch; do not blindly edit/redrive |
| Missing or unexpected receipts | Suspend affected downstream workflow; compare entry, outbox and receipt evidence in a restricted offline copy |
| Token exposure | Rotate both affected credentials, restart service, review access evidence |

No automatic quarantine redrive is provided; create a reviewed repair procedure before introducing it. Reconciliation is aggregate workflow consistency, not monetary balancing. The operator report exposes oldest pending timestamp but does not enforce a backlog-age threshold.

## Backup and restore (local)

Run `python -m app.admin backup work/backup.db` with a new destination. The SQLite online backup interface copies a consistent snapshot and validates integrity. For Compose use `docker compose exec api python -m app.admin backup /data/backup.db` then export the file with `docker compose cp api:/data/backup.db ./backup.db`. Keep backups in restricted storage off the source volume.

For restore, stop API and worker. Preserve the original DB and WAL/SHM files. Copy a known backup into a **new** location and set `SERVICING_DB_PATH` to that path for API, worker and offline admin. Run `python -m app.admin reconcile`, verify expected entries, then restart and smoke-check. Do not overwrite a live DB or copy only its main file while WAL writes are active. Record snapshot time, restore time and discrepancy results. Local restore was tested; no disaster recovery RTO/RPO is claimed.
