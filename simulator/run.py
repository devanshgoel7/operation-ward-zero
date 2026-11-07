import json
import logging
import os
import random
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError
from http.client import HTTPException
from pathlib import Path
from threading import Event
from urllib.request import Request, urlopen

from simulator.buffer import DEVICE_IDS, connect, generate, initialize


def retry_delay(attempts: int, retry_after: str | None) -> float:
    base = min(2 ** min(attempts, 4), 15)
    delay = random.uniform(base * 0.8, base)
    if retry_after:
        try:
            if retry_after.isascii() and retry_after.isdigit():
                return max(delay, int(retry_after))
            return max(delay, parsedate_to_datetime(retry_after).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            pass
    return delay


def upload_one(connection: sqlite3.Connection, url: str, key: str) -> bool:
    frame = connection.execute("""
        SELECT * FROM frames WHERE status = 'pending' ORDER BY rowid LIMIT 1
    """).fetchone()
    if frame is None or frame["next_retry"] > time.time():
        return False
    request = Request(url, data=frame["payload"].encode(), headers={
        "Content-Type": "application/json", "X-Simulator-Key": key,
    })
    try:
        with urlopen(request, timeout=3) as response:
            receipt = json.load(response)
            expected = {200: "duplicate", 201: "accepted"}.get(response.status)
            if (not isinstance(receipt, dict) or expected is None
                    or receipt.get("reading_id") != frame["reading_id"]
                    or receipt.get("disposition") != expected):
                raise ValueError("Server returned an unexpected reading receipt.")
    except (OSError, HTTPException, ValueError) as exc:
        retry_after = None
        if isinstance(exc, HTTPError):
            retry_after = exc.headers.get("Retry-After")
            exc.close()
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                logging.error("Reading %s quarantined: %s", frame["reading_id"], exc)
                connection.execute("""UPDATE frames SET status='quarantined', attempts=attempts+1,
                    next_retry=0, last_error=? WHERE reading_id=?""", (str(exc), frame["reading_id"]))
                return True
        delay = retry_delay(frame["attempts"], retry_after)
        logging.warning("Reading %s pending: %s", frame["reading_id"], exc)
        connection.execute("""
            UPDATE frames SET attempts = attempts + 1, next_retry = ?, last_error = ? WHERE reading_id = ?
        """, (time.time() + delay, str(exc), frame["reading_id"]))
        return False
    connection.execute("""
        UPDATE frames SET status = 'accepted', attempts = attempts + 1, next_retry = 0,
                          last_error = NULL WHERE reading_id = ?
    """, (frame["reading_id"],))
    return True


def upload_loop(path: Path, url: str, key: str, stop: Event) -> None:
    with closing(connect(path)) as connection:
        while not stop.is_set():
            if not upload_one(connection, url, key):
                stop.wait(0.25)


def main() -> None:
    path = Path(os.environ["BUFFER_PATH"])
    url = os.environ["INGEST_URL"]
    key = os.environ["SIMULATOR_KEY"]
    stop = Event()
    with closing(connect(path)) as connection, ThreadPoolExecutor(max_workers=1) as pool:
        initialize(connection)
        uploader = pool.submit(upload_loop, path, url, key, stop)
        try:
            while True:
                observed = datetime.now(UTC)
                for device_id in DEVICE_IDS:
                    generate(connection, device_id, observed)
                try:
                    uploader.result(timeout=5)
                except TimeoutError:
                    if uploader.done():
                        raise
        finally:
            stop.set()


if __name__ == "__main__":
    main()
