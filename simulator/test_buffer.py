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


class BufferTests(unittest.TestCase):
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
