ALTER TABLE outbox ADD COLUMN quarantined_at TEXT;
ALTER TABLE outbox ADD COLUMN failure_code TEXT;
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
CREATE INDEX audit_entry_idx ON audit_events(entry_id, event_type);
CREATE INDEX outbox_entry_idx ON outbox(entry_id);
