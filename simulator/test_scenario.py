import json
import unittest
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from simulator.buffer import DEVICE_IDS, connect, generate, initialize
from simulator.scenario import select
from simulator.trigger_alert import queue_alert


class ScenarioTests(unittest.TestCase):
    def test_persisted_selection_controls_committed_frames_and_preserves_sequence(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "frames.sqlite3"
            with closing(connect(path)) as conn:
                initialize(conn)
                queue_alert(conn, DEVICE_IDS[0])
                select(conn, DEVICE_IDS[0], "deterioration")
            with closing(connect(path)) as conn:
                for name, expected in (("deterioration", (90, 96)), ("missing", (70, None)),
                                       ("recovery", (70, 99)), ("stable", (70, 99))):
                    select(conn, DEVICE_IDS[0], name)
                    identifier = generate(conn, DEVICE_IDS[0], datetime.now(UTC))
                    with closing(connect(path)) as reader:
                        row = reader.execute("SELECT * FROM frames WHERE reading_id=?", (identifier,)).fetchone()
                        payload = json.loads(row["payload"])
                        self.assertEqual((payload["heart_rate_bpm"], payload["spo2_pct"]), expected)
                        self.assertEqual(row["status"], "pending")
                self.assertEqual([r[0] for r in conn.execute("SELECT sequence FROM frames ORDER BY sequence")], [1, 2, 3, 4])
                self.assertEqual(conn.execute("SELECT count(*) FROM alert_demo").fetchone()[0], 0)
                with self.assertRaises(ValueError):
                    select(conn, DEVICE_IDS[0], "unknown")
