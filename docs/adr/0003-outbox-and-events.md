# ADR-0003: Transactional outbox and asynchronous events

- **Status:** Accepted.
- **Context:** Publishing directly after a database commit can lose an event; publishing before commit can expose an event for a rolled-back record.
- **Decision:** Persist a versioned event in an outbox in the same transaction as the entry, then publish asynchronously to SQS Standard.
- **Alternatives:** Dual writes; database change data capture; synchronous downstream call; event sourcing.
- **Rationale:** The outbox makes intent durable at the database transaction boundary and keeps downstream slowness out of the request path.
- **Consequences:** Publisher retries may duplicate messages; consumer receipts and business effects must be atomic. Monitor outbox age, queue age, and DLQ.
- **Security / operations:** Minimize payload fields, encrypt queues, constrain IAM send/receive permissions, and make redrive an approved operation.
- **Cost:** SQS cost is likely smaller than EKS/RDS base cost; logs, traffic, and downstream retention still count.
- **Revisit when:** Event volume or latency needs justify CDC or another broker and its operational burden.

