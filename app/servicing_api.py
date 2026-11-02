"""Synthetic servicing-entry API. No real payment or servicing integration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


DB_PATH = Path(os.environ.get("SERVICING_DB_PATH", "./work/servicing.db"))
HOST = os.environ.get("SERVICING_HOST", "0.0.0.0")
PORT = int(os.environ.get("SERVICING_PORT", "8080"))
MAX_BODY_BYTES = 16_384
LOAN_REF_RE = re.compile(r"^SYN-[A-Z0-9-]{4,40}$")
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def initialize_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
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
            """
        )


def normalize_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("body must be a JSON object")
    loan_ref = value.get("loan_ref")
    amount_cents = value.get("amount_cents")
    currency = value.get("currency")
    effective_date = value.get("effective_date")
    if not isinstance(loan_ref, str) or not LOAN_REF_RE.fullmatch(loan_ref):
        raise ValueError("loan_ref must use a synthetic SYN- prefix and valid characters")
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ValueError("amount_cents must be a positive integer")
    if amount_cents > 100_000_000:
        raise ValueError("amount_cents exceeds the simulator limit")
    if currency != "USD":
        raise ValueError("currency must be USD in this synthetic demo")
    if not isinstance(effective_date, str):
        raise ValueError("effective_date must be an ISO date")
    try:
        date.fromisoformat(effective_date)
    except ValueError as exc:
        raise ValueError("effective_date must be an ISO date") from exc
    return {
        "loan_ref": loan_ref,
        "amount_cents": amount_cents,
        "currency": currency,
        "effective_date": effective_date,
    }


def request_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def entry_dict(row: sqlite3.Row, *, replayed: bool = False) -> dict[str, Any]:
    return {
        "entry_id": row["entry_id"],
        "loan_ref": row["loan_ref"],
        "amount_cents": row["amount_cents"],
        "currency": row["currency"],
        "effective_date": row["effective_date"],
        "state": row["state"],
        "version": row["version"],
        "created_at": row["created_at"],
        "idempotency_replayed": replayed,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ServicingLedgerDemo/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep request bodies, loan references, and idempotency keys out of logs.
        super().log_message(fmt, *args)

    def send_json(self, status: int, value: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for key, val in (headers or {}).items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        if path == "/readyz":
            try:
                with connect() as conn:
                    conn.execute("SELECT 1").fetchone()
                self.send_json(200, {"status": "ready"})
            except sqlite3.Error:
                self.send_json(503, {"status": "not_ready"})
            return
        prefix = "/v1/servicing-entries/"
        if path.startswith(prefix):
            entry_id = unquote(path[len(prefix):])
            with connect() as conn:
                row = conn.execute(
                    "SELECT * FROM servicing_entries WHERE entry_id = ?", (entry_id,)
                ).fetchone()
            if row is None:
                self.send_json(404, {"error": "NOT_FOUND"})
            else:
                self.send_json(200, entry_dict(row))
            return
        self.send_json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urlparse(self.path).path != "/v1/servicing-entries":
            self.send_json(404, {"error": "NOT_FOUND"})
            return
        idem_key = self.headers.get("Idempotency-Key", "")
        if not IDEMPOTENCY_RE.fullmatch(idem_key):
            self.send_json(400, {"error": "INVALID_IDEMPOTENCY_KEY"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "INVALID_CONTENT_LENGTH"})
            return
        if length < 1 or length > MAX_BODY_BYTES:
            self.send_json(413 if length > MAX_BODY_BYTES else 400, {"error": "INVALID_BODY_SIZE"})
            return
        try:
            body = json.loads(self.rfile.read(length))
            payload = normalize_request(body)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self.send_json(400, {"error": "INVALID_REQUEST", "detail": str(exc)})
            return

        digest = request_digest(payload)
        now = utc_now()
        entry_id = "se_" + uuid.uuid4().hex
        event_id = "evt_" + uuid.uuid4().hex
        event = {
            "event_id": event_id,
            "event_type": "servicing.entry.recorded.v1",
            "entry_id": entry_id,
            "loan_ref": payload["loan_ref"],
            "amount_cents": payload["amount_cents"],
            "currency": payload["currency"],
            "effective_date": payload["effective_date"],
            "occurred_at": now,
        }

        try:
            with connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT * FROM servicing_entries WHERE idempotency_key = ?", (idem_key,)
                ).fetchone()
                if existing is not None:
                    conn.rollback()
                    if existing["request_hash"] != digest:
                        self.send_json(409, {"error": "IDEMPOTENCY_CONFLICT"})
                    else:
                        self.send_json(200, entry_dict(existing, replayed=True), {
                            "Idempotency-Replayed": "true"
                        })
                    return

                conn.execute(
                    """INSERT INTO servicing_entries
                    (entry_id, idempotency_key, request_hash, loan_ref, amount_cents,
                     currency, effective_date, state, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'RECORDED', ?)""",
                    (entry_id, idem_key, digest, payload["loan_ref"], payload["amount_cents"],
                     payload["currency"], payload["effective_date"], now),
                )
                conn.execute(
                    "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                    ("aud_" + uuid.uuid4().hex, entry_id, "servicing.entry.recorded",
                     now, json.dumps(event, sort_keys=True, separators=(",", ":"))),
                )
                conn.execute(
                    "INSERT INTO outbox VALUES (?, ?, ?, ?, ?, NULL)",
                    (event_id, entry_id, event["event_type"],
                     json.dumps(event, sort_keys=True, separators=(",", ":")), now),
                )
                conn.commit()
        except sqlite3.Error:
            self.send_json(503, {"error": "TEMPORARY_STORAGE_FAILURE"})
            return

        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM servicing_entries WHERE entry_id = ?", (entry_id,)
            ).fetchone()
        self.send_json(201, entry_dict(row), {"Location": f"/v1/servicing-entries/{entry_id}"})


def main() -> None:
    initialize_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"servicing-ledger demo listening on {HOST}:{PORT}; database={DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

