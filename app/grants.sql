-- Apply after each migration as ledger_migrator (schema owner). No runtime role owns tables.
GRANT USAGE ON SCHEMA ledger TO ledger_api, ledger_publisher, ledger_consumer, ledger_archive;
GRANT SELECT ON ledger_schema TO ledger_api, ledger_publisher, ledger_consumer, ledger_archive;
GRANT SELECT ON servicing_entries, audit_events, outbox, consumer_receipts, audit_archive_receipts TO ledger_api;
GRANT INSERT ON servicing_entries, audit_events, outbox TO ledger_api;
GRANT SELECT ON outbox TO ledger_publisher, ledger_consumer;
GRANT UPDATE (published_at, quarantined_at, failure_code) ON outbox TO ledger_publisher;
GRANT UPDATE (handled_at) ON outbox TO ledger_consumer;
GRANT INSERT ON audit_events, consumer_receipts TO ledger_consumer;
GRANT SELECT ON consumer_receipts TO ledger_consumer;
GRANT SELECT ON audit_events, audit_archive_receipts TO ledger_archive;
GRANT INSERT ON audit_archive_receipts TO ledger_archive;
