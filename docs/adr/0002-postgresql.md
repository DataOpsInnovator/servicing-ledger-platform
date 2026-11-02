# ADR-0002: PostgreSQL as the transaction source of truth

- **Status:** Accepted for AWS reference; SQLite is used only by the local simulator.
- **Context:** Entry, idempotency key, audit event, and outbox event need one atomic commit and unique constraints.
- **Decision:** Use Amazon RDS for PostgreSQL as the reference persistence layer.
- **Alternatives:** DynamoDB conditional/transaction writes; Aurora PostgreSQL; event sourcing as the system of record.
- **Rationale:** Relational constraints and transactions make the invariant easy to inspect and reconcile; RDS limits database operations compared with self-managed PostgreSQL.
- **Consequences:** Connection pooling, schema migrations, failover recovery, and backup retention still need ownership. SQLite's behavior is not a substitute for validating PostgreSQL concurrency.
- **Security / operations:** Private subnets, encryption, scoped credentials, TLS, restricted snapshots, and restore rehearsal.
- **Cost:** Multi-AZ doubles/raises database cost; start with disposable Single-AZ only when availability claims are explicitly excluded.
- **Revisit when:** Measured access patterns, scale, or operational constraints justify DynamoDB or Aurora.

