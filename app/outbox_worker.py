"""Local outbox/consumer simulator. Not an AWS SQS client."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from servicing_api import connect, initialize_db, utc_now


CONSUMER_NAME = "local-ledger-projection-v1"


def handle_batch(limit: int = 50) -> int:
    handled = 0
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT * FROM outbox WHERE handled_at IS NULL ORDER BY created_at, event_id LIMIT ?",
            (limit,),
        ).fetchall()
        for row in rows:
            now = utc_now()
            cursor = conn.execute(
                "INSERT OR IGNORE INTO consumer_receipts VALUES (?, ?, ?)",
                (CONSUMER_NAME, row["event_id"], now),
            )
            if cursor.rowcount == 1:
                event: dict[str, Any] = json.loads(row["payload_json"])
                conn.execute(
                    "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                    ("aud_" + uuid.uuid4().hex, row["entry_id"],
                     "servicing.entry.consumer_recorded", now,
                     json.dumps({"event_id": row["event_id"], "event_type": event["event_type"]},
                                sort_keys=True, separators=(",", ":"))),
                )
                handled += 1
            conn.execute("UPDATE outbox SET handled_at = ? WHERE event_id = ?", (now, row["event_id"]))
        conn.commit()
    return handled


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="handle one batch and exit")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    initialize_db()
    while True:
        try:
            count = handle_batch()
            if count:
                print(f"local worker recorded {count} new event receipt(s)")
        except sqlite3.Error as exc:
            print(f"local worker storage error: {exc.__class__.__name__}", file=sys.stderr)
        if args.once:
            return
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()

