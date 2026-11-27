ALTER TABLE outbox ADD COLUMN quarantined_at TEXT;
ALTER TABLE outbox ADD COLUMN failure_code TEXT;
CREATE FUNCTION reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'append-only table'; END; $$;
CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE INDEX audit_entry_idx ON audit_events(entry_id, event_type);
CREATE INDEX outbox_entry_idx ON outbox(entry_id);
