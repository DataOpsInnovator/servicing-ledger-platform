ALTER TABLE servicing_entries ADD COLUMN reversal_of TEXT REFERENCES servicing_entries(entry_id);
ALTER TABLE servicing_entries ADD COLUMN reversal_reason TEXT;
CREATE UNIQUE INDEX one_reversal_per_entry ON servicing_entries(reversal_of) WHERE reversal_of IS NOT NULL;
ALTER TABLE outbox ADD COLUMN published_at TEXT;
CREATE TABLE audit_archive_receipts (audit_id TEXT PRIMARY KEY REFERENCES audit_events(audit_id), archived_at TEXT NOT NULL);
CREATE TRIGGER entry_no_update BEFORE UPDATE ON servicing_entries BEGIN SELECT RAISE(ABORT, 'entries are append-only'); END;
CREATE TRIGGER entry_no_delete BEFORE DELETE ON servicing_entries BEGIN SELECT RAISE(ABORT, 'entries are append-only'); END;
CREATE TRIGGER valid_reversal BEFORE INSERT ON servicing_entries
WHEN (NEW.reversal_of IS NULL AND NEW.reversal_reason IS NOT NULL)
  OR (NEW.reversal_of IS NOT NULL AND (NEW.reversal_reason IS NULL OR NEW.reversal_reason NOT IN ('DUPLICATE','INCORRECT_AMOUNT','INCORRECT_DATE','OPERATIONAL_ERROR') OR NOT EXISTS (
    SELECT 1 FROM servicing_entries e WHERE e.entry_id=NEW.reversal_of AND e.reversal_of IS NULL
    AND e.loan_ref=NEW.loan_ref AND e.amount_cents=NEW.amount_cents AND e.currency=NEW.currency AND e.effective_date<=NEW.effective_date)))
BEGIN SELECT RAISE(ABORT, 'invalid reversal'); END;
