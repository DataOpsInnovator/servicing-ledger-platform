# Security policy

Synthetic reference only. Do not enter real customer records, account numbers or payments. Report security issues privately to the repository maintainer (configure GitHub private vulnerability reporting before publishing); do not post secrets or exploitable details publicly. Supported release: v2.0.0 source, pending independent validation.

## Controls

Role-scoped API and RS256 OIDC, trusted issuer/audience/JWKS, bounded input, strict validation, append-only journal, pseudonymous actor, atomic DB transactions, per-workload IAM/DB roles, TLS PostgreSQL, SQS encryption/redrive, immutable audit archive default retention, scoped network ingress, private infrastructure, signed image and vulnerability gates. Local token mode is not enterprise identity. Runtime secrets fetched at startup and require controlled rotation. Object-lock retention only protects archived object versions and is not a complete audit or compliance system.

## Remaining approval gates

Run real PostgreSQL/role tests and cloud acceptance, resolve dependency/container/IaC findings, pin actions and image inputs, validate trust/issuer/scopes, workload identity/DB grants, secret rotation, CNI egress and TLS end-to-end, admission-time signature enforcement, backup/failover/PITR, cloud log retention, external reconciliation and maker-checker approval. No regulatory compliance certification. See `docs/cloud-deployment.md` and `docs/operations-v2.md`.
