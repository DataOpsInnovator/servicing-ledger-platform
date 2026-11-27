# ADR-0013: v2 cloud runtime, correction and evidence boundaries

**Status:** accepted for reference implementation; AWS verification pending.

Use PostgreSQL with DB-scoped advisory locks, role grants and transactional outbox to support distributed API replicas. Retain SQLite for offline evaluation. Use SQS Standard and deduplicated receipts rather than claim exactly-once delivery. Model corrections as immutable full reversal entries, not in-place updates. Use separately controlled migration role and EKS Pod Identity per runtime. Archive audit events conditionally into an Object Lock bucket; archive lag and retention approval are explicit risks. Deploy digest-pinned workloads through reviewed Argo sync and verify signatures at promotion. Do not promote to live business production until cloud acceptance, security review, controls and recovery gates pass.

Trade-offs: simpler modular service and single-event publishing over throughput optimizations; single-organization synthetic journal over a full accounting platform. Native AWS Terraform resources improve readability at the cost of maintaining provider compatibility and add-on versions. Cloud deployment is expensive compared with SQLite; use local or disposable PostgreSQL for interviews and routine development.
