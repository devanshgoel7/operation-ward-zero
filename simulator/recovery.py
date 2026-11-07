"""Inspect a durable buffer, drain with generation stopped, or verify against PostgreSQL IDs."""
import argparse
import json
import os
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

from simulator.buffer import connect
from simulator.run import upload_one


def reconcile(connection: sqlite3.Connection, server: set[str], require_drained: bool) -> dict:
    local = {row["reading_id"]: row["status"] for row in connection.execute("SELECT reading_id, status FROM frames")}
    pending = {key for key, state in local.items() if state == "pending"}
    quarantined = {key for key, state in local.items() if state == "quarantined"}
    accepted = {key for key, state in local.items() if state == "accepted"}
    differences = {
        "accepted_missing_on_server": sorted(accepted - server),
        "unexpected_server_ids": sorted(server - local.keys()),
        "overlapping_ids": sorted(server & (pending | quarantined)),
        "unknown_status": sorted(local.keys() - accepted - pending - quarantined),
    }
    return {"generated": len(local), "server": len(server), "pending": len(pending),
            "quarantined": len(quarantined), **differences,
            "ok": not any(differences.values()) and not (require_drained and (pending or quarantined))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "drain", "verify"))
    parser.add_argument("--require-drained", action="store_true")
    args = parser.parse_args()
    path = Path(os.environ["BUFFER_PATH"])
    if not path.is_file():
        raise SystemExit("Missing simulator buffer.")
    with closing(connect(path)) as conn:
        if args.command == "verify":
            result = reconcile(conn, {line.strip() for line in sys.stdin if line.strip()}, args.require_drained)
            print(json.dumps(result))
            raise SystemExit(0 if result["ok"] else 1)
        if args.command == "drain":
            deadline = time.monotonic() + 120
            while conn.execute("SELECT 1 FROM frames WHERE status='pending' LIMIT 1").fetchone():
                if time.monotonic() > deadline:
                    raise SystemExit("Drain timed out. Inspect status before retrying.")
                if not upload_one(conn, os.environ["INGEST_URL"], os.environ["SIMULATOR_KEY"]):
                    time.sleep(0.25)
        counts = dict(conn.execute("SELECT status,count(*) FROM frames GROUP BY status"))
        errors = [dict(row) for row in conn.execute("""SELECT reading_id,status,attempts,next_retry,last_error
            FROM frames WHERE last_error IS NOT NULL ORDER BY rowid DESC LIMIT 10""")]
        print(json.dumps({"counts": counts, "recent_errors": errors}))


if __name__ == "__main__":
    main()
