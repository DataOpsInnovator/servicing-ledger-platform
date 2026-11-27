CREATE TABLE IF NOT EXISTS servicing_entries (
    entry_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL,
    loan_ref TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    effective_date TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('RECORDED')),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    audit_id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES servicing_entries(entry_id),
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    event_id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES servicing_entries(entry_id),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    handled_at TEXT
);
CREATE INDEX IF NOT EXISTS outbox_pending_idx
    ON outbox(handled_at, created_at);
CREATE TABLE IF NOT EXISTS consumer_receipts (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    received_at TEXT NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
