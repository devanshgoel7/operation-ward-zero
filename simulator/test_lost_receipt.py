"""Compose fixture: run with sampling stopped and the isolated test buffer drained."""
import json
import os
from contextlib import closing
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

from simulator.buffer import DEVICE_IDS, connect, generate
from simulator.run import upload_one
from simulator.trigger_alert import queue_alert


def main() -> None:
    dest = os.environ["INGEST_URL"]
    key = os.environ["SIMULATOR_KEY"]
    receipts = []

    class LoseReceipt(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            request = Request(dest, data=body, headers={"Content-Type": "application/json", "X-Simulator-Key": key})
            with urlopen(request, timeout=3) as response:
                assert response.status == 201
                receipts.append(json.load(response))
            # Closing the client socket without sending headers loses the real committed receipt.
            self.close_connection = True

    with closing(connect(Path(os.environ["BUFFER_PATH"]))) as conn, HTTPServer(("127.0.0.1", 0), LoseReceipt) as proxy:
        assert not conn.execute("SELECT 1 FROM frames WHERE status='pending'").fetchone()
        queue_alert(conn, DEVICE_IDS[0])
        reading_id = generate(conn, DEVICE_IDS[0], datetime.now(UTC))
        thread = Thread(target=proxy.handle_request, daemon=True)
        thread.start()
        assert not upload_one(conn, f"http://127.0.0.1:{proxy.server_port}", key)
        thread.join(timeout=5)
        assert receipts and receipts[0]["reading_id"] == reading_id
        assert conn.execute("SELECT status FROM frames WHERE reading_id=?", (reading_id,)).fetchone()[0] == "pending"
        conn.execute("UPDATE frames SET next_retry=0 WHERE reading_id=?", (reading_id,))
        assert upload_one(conn, dest, key)
        saved = conn.execute("SELECT attempts,status FROM frames WHERE reading_id=?", (reading_id,)).fetchone()
        assert tuple(saved) == (2, "accepted")
        print(json.dumps(receipts[0]))


if __name__ == "__main__":
    main()
