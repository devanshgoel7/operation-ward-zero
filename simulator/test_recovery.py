import json
import sqlite3
import unittest
from contextlib import closing
from datetime import UTC, datetime
from email.message import Message
from email.utils import formatdate
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError

from simulator.buffer import DEVICE_IDS, connect, generate, initialize
from simulator.recovery import reconcile
from simulator.run import retry_delay, upload_one


class RecoveryTests(unittest.TestCase):
    def test_retry_and_quarantine(self):
        with TemporaryDirectory() as directory, closing(connect(Path(directory) / "db")) as conn:
            initialize(conn)
            first, second = [generate(conn, device, datetime.now(UTC)) for device in DEVICE_IDS[:2]]
            headers = Message()
            headers["Retry-After"] = "21"
            with patch("simulator.run.time.time", return_value=100):
                for code in [408, 429, 500, 503]:
                    with patch("simulator.run.urlopen", side_effect=HTTPError("http://app", code, "retry", headers, None)):
                        conn.execute("UPDATE frames SET next_retry=0")
                        self.assertFalse(upload_one(conn, "http://app", "test"))
                        saved = conn.execute("SELECT * FROM frames WHERE reading_id=?", (first,)).fetchone()
                        self.assertEqual((saved["status"], saved["next_retry"]), ("pending", 121))
                self.assertEqual(retry_delay(1, formatdate(130, usegmt=True)), 30)
                self.assertLessEqual(retry_delay(100, "invalid"), 15)
                for identifier, code in [(first, 422), (second, 409)]:
                    conn.execute("UPDATE frames SET next_retry=0")
                    with patch("simulator.run.urlopen", side_effect=HTTPError("http://app", code, "permanent", headers, None)):
                        self.assertTrue(upload_one(conn, "http://app", "test"))
                        row = conn.execute("SELECT * FROM frames WHERE reading_id=?", (identifier,)).fetchone()
                        self.assertEqual(row["status"], "quarantined")
                        self.assertEqual(json.loads(row["payload"])["reading_id"], identifier)
                        self.assertIn(str(code), row["last_error"])

    def test_verify_compares_identifiers_and_disjoint_statuses(self):
        with TemporaryDirectory() as directory, closing(connect(Path(directory) / "db")) as conn:
            initialize(conn)
            stored, pending, invalid = [generate(conn, device, datetime.now(UTC)) for device in DEVICE_IDS]
            conn.execute("UPDATE frames SET status='accepted' WHERE reading_id=?", (stored,))
            conn.execute("UPDATE frames SET status='quarantined' WHERE reading_id=?", (invalid,))
            self.assertTrue(reconcile(conn, {stored}, False)["ok"])
            self.assertFalse(reconcile(conn, {stored}, True)["ok"])
            for wrong in ({pending}, {invalid}, {"unknown"}, set(), {stored, pending}):
                self.assertFalse(reconcile(conn, wrong, False)["ok"])

    def test_local_storage_failure_stops_generation_before_upload(self):
        with TemporaryDirectory() as directory, closing(connect(Path(directory) / "db")) as conn:
            initialize(conn)
            conn.execute("PRAGMA query_only=ON")
            with self.assertRaises(sqlite3.OperationalError):
                generate(conn, DEVICE_IDS[0], datetime.now(UTC))
            self.assertEqual(conn.execute("SELECT count(*) FROM frames").fetchone()[0], 0)
