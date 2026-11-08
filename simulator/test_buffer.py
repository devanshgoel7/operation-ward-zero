import json
import unittest
from contextlib import closing
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import URLError

from simulator.buffer import DEVICE_IDS, connect, generate, initialize
from simulator.run import upload_one
from simulator.trigger_alert import main as trigger, queue_alert


class BufferTests(unittest.TestCase):
    def test_default_rotation_wraps_across_invocations(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "frames.sqlite3"
            with closing(connect(path)) as connection, patch.dict("os.environ", BUFFER_PATH=str(path)), patch("sys.argv", ["trigger"]):
                initialize(connection)
                for device in (*DEVICE_IDS, DEVICE_IDS[0]):
                    trigger()
                    self.assertEqual(connection.execute("SELECT device_id FROM alert_demo").fetchone()[0], str(device))
                    for _ in range(6):
                        generate(connection, device, datetime.now(UTC))

    def test_live_alert_sequence_is_patient_specific_and_resumes_baseline(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "frames.sqlite3"
            with closing(connect(path)) as connection:
                initialize(connection)
                generate(connection, DEVICE_IDS[0], datetime.now(UTC))
                self.assertTrue(queue_alert(connection, DEVICE_IDS[0]))
                self.assertFalse(queue_alert(connection, DEVICE_IDS[0]))
            with closing(connect(path)) as connection:
                for _ in range(7):
                    for device in DEVICE_IDS:
                        generate(connection, device, datetime.now(UTC))
                for index, device in enumerate(DEVICE_IDS):
                    rows = connection.execute("SELECT payload FROM frames WHERE device_id = ? ORDER BY sequence",
                                              (str(device),))
                    payloads = [json.loads(row["payload"]) for row in rows]
                    oxygen = [payload["spo2_pct"] for payload in payloads]
                    if index == 0:
                        self.assertEqual(oxygen[1:7], [93] * 3 + [88] * 3)
                        heart_rates = [payload["heart_rate_bpm"] for payload in payloads]
                        self.assertEqual(heart_rates[2:4], [115, 115])
                        self.assertLessEqual(max(heart_rates[:2] + heart_rates[4:]), 110)
                        self.assertGreaterEqual(min(oxygen[0], oxygen[-1]), 96)
                    else:
                        self.assertGreaterEqual(min(oxygen), 96)
                self.assertTrue(queue_alert(connection, DEVICE_IDS[0]))

    def test_committed_payload_reused_on_retry(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "frames.sqlite3"
            with closing(connect(path)) as writer:
                initialize(writer)
                reading_id = generate(writer, DEVICE_IDS[0], datetime.now(UTC))
            with closing(connect(path)) as reader:
                frame = reader.execute("SELECT * FROM frames").fetchone()
                self.assertEqual((frame["reading_id"], frame["status"], frame["attempts"]), (reading_id, "pending", 0))
                self.assertEqual(reader.execute("PRAGMA synchronous").fetchone()[0], 2)
                response = BytesIO(json.dumps({"reading_id": reading_id, "disposition": "duplicate"}).encode())
                response.status = 200
                with patch("simulator.run.time.time", return_value=100), patch(
                    "simulator.run.urlopen", side_effect=[URLError("offline"), response]
                ) as send:
                    self.assertFalse(upload_one(reader, "http://app/readings", "key"))
                    self.assertFalse(upload_one(reader, "http://app/readings", "key"))
                    self.assertEqual(send.call_count, 1)
                    with patch("simulator.run.time.time", return_value=101):
                        self.assertTrue(upload_one(reader, "http://app/readings", "key"))
                    self.assertEqual([call.args[0].data for call in send.call_args_list], [frame["payload"].encode()] * 2)
                saved = reader.execute("SELECT * FROM frames").fetchone()
                self.assertEqual((saved["status"], saved["attempts"], saved["last_error"]), ("accepted", 2, None))
                generate(reader, DEVICE_IDS[0], datetime.now(UTC))
                self.assertEqual(reader.execute("SELECT MAX(sequence) FROM frames").fetchone()[0], 2)
