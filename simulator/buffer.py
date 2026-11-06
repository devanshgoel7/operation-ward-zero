import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4


DEVICE_IDS = tuple(UUID(f"30000000-0000-0000-0000-{n:012d}") for n in range(1, 4))


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS frames (
            reading_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, next_retry REAL NOT NULL DEFAULT 0,
            last_error TEXT, UNIQUE (device_id, sequence)
        );
        CREATE INDEX IF NOT EXISTS pending_frames ON frames(status);
    """)


def generate(connection: sqlite3.Connection, device_id: UUID, observed: datetime) -> str:
    connection.execute("BEGIN IMMEDIATE")
    try:
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM frames WHERE device_id = ?", (str(device_id),)
        ).fetchone()[0]
        reading_id = str(uuid4())
        variation = (sequence + device_id.int) % 5
        frame = {
            "reading_id": reading_id, "device_id": str(device_id), "sequence": sequence,
            "observed_at": observed.astimezone(UTC).isoformat(), "heart_rate_bpm": 70 + variation,
            "spo2_pct": 96 + variation % 3, "systolic_mmhg": 115 + variation,
            "diastolic_mmhg": 75 + variation, "temperature_c": 36.5 + variation / 10,
        }
        connection.execute("""
            INSERT INTO frames (reading_id, device_id, sequence, payload) VALUES (?, ?, ?, ?)
        """, (reading_id, str(device_id), sequence, json.dumps(frame)))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return reading_id
