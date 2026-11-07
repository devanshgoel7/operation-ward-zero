"""Run real M3 failures in a new isolated Compose project, retaining both volumes as evidence."""
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def wait_until(label, probe, timeout=80):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = probe()
        if result:
            return result
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {label}")


def main() -> None:
    project = "wardzero-m3-" + uuid4().hex[:10]
    print(f"Verification project {project}", flush=True)
    env = os.environ | {"APP_PORT": "0"}
    def run(*args, stdin=None):
        return subprocess.run(["docker", *args], cwd=ROOT, env=env, input=stdin, text=True,
                              stdout=subprocess.PIPE, check=True, timeout=240).stdout.strip()

    def compose(*args, stdin=None):
        return run("compose", "-p", project, *args, stdin=stdin)

    def database(sql):
        return compose("exec", "-T", "db", "psql", "-v", "ON_ERROR_STOP=1", "-U", "wardzero", "-Atc", sql)

    def simulator(*args):
        return compose("exec", "-T", "simulator", "python", *args)

    def oneshot(*args, stdin=None):
        return compose("run", "--rm", "-T", "--no-deps", "simulator", "python", "-m", *args, stdin=stdin)

    def status():
        return json.loads(simulator("-m", "simulator.recovery", "status"))["counts"]

    def pending():
        return status().get("pending", 0)

    def buffered():
        code = """import sqlite3,os,json
c=sqlite3.connect(os.environ['BUFFER_PATH'])
print(json.dumps(c.execute('SELECT reading_id,device_id,sequence,status FROM frames ORDER BY rowid').fetchall()))"""
        return json.loads(simulator("-c", code))

    try:
        compose("up", "--build", "-d", "--wait", "--wait-timeout", "120")
        base = "http://" + compose("port", "app", "8000")
        def get(path):
            with urlopen(base + path, timeout=6) as response:
                return json.load(response)
        wait_until("initial delivery", lambda: status().get("accepted", 0) >= 3 and not pending())
        container = compose("ps", "-q", "simulator")
        network = project + "_default"
        run("network", "disconnect", network, container)
        try:
            initial = status().get("accepted", 0)
            simulator("-m", "simulator.trigger_alert")
            queued_at = time.monotonic()
            wait_until("six offline samples", lambda: pending() >= 6)
            def stale_gap():
                snapshot = get("/api/v1/dashboard")
                return (all(p["data_quality"] == "stale" for p in snapshot["patients"])
                        and sum(a["kind"] == "monitoring_gap" for a in snapshot["active_alerts"]) == 3)
            wait_until("three stale cards and three gap episodes", stale_gap)
            wait_until("first offline concern older than 30 seconds", lambda: time.monotonic() - queued_at > 37)
            assert status().get("accepted", 0) == initial
            print(f"Network disconnected: {pending()} pending, three stale patients and three gaps.", flush=True)
        finally:
            run("network", "connect", network, container)
        wait_until("network backlog drained", lambda: not pending())
        wait_until("historical concern", lambda: any(a["kind"] == "delayed_review" for a in get("/api/v1/dashboard")["active_alerts"]))
        compose("stop", "app")
        wait_until("backend outage backlog", lambda: pending() >= 3)
        before = buffered()
        compose("restart", "simulator")
        wait_until("sampling after restart", lambda: len(buffered()) >= len(before) + 3)
        after = buffered()
        assert after[:len(before)] == before
        for device in {r[1] for r in before}:
            old = max(r[2] for r in before if r[1] == device)
            new = [r for r in after[len(before):] if r[1] == device]
            assert new and new[0][2] == old + 1 and all(r[3] == "pending" for r in new)
        # Make one persisted deadline overdue while the app is stopped.
        review = database("SELECT id FROM alerts WHERE kind='delayed_review' AND status='open' LIMIT 1")
        database(f"UPDATE alerts SET escalation_due_at=now() WHERE id='{review}'")
        compose("up", "-d", "--wait", "app")
        base = "http://" + compose("port", "app", "8000")
        detail = get(f"/api/v1/alerts/{review}")
        assert sum(e["event_type"] == "escalated" for e in detail["events"]) == 1
        wait_until("backend backlog drained", lambda: not pending())
        print("App outage: buffered IDs and per-device sequences survived simulator restart. Overdue review escalated once.", flush=True)
        compose("stop", "db")
        try:
            assert get("/health/live")["status"] == "live"
            try:
                get("/health/ready")
            except HTTPError as error:
                assert error.code == 503
            else:
                raise AssertionError("Ready during database outage")
            # Repost a previously committed valid payload. Even a duplicate needs a DB commit.
            probe = """import os,sqlite3
from urllib.request import Request,urlopen
from urllib.error import HTTPError
c=sqlite3.connect(os.environ['BUFFER_PATH'])
payload=c.execute("SELECT payload FROM frames WHERE status='accepted' LIMIT 1").fetchone()[0]
try:
    urlopen(Request(os.environ['INGEST_URL'],data=payload.encode(),headers={'X-Simulator-Key':os.environ['SIMULATOR_KEY'],'Content-Type':'application/json'}),timeout=8)
except HTTPError as error:
    assert error.code == 503
else:
    raise AssertionError('False acknowledgement')"""
            simulator("-c", probe)
            prior = status().get("accepted", 0)
            wait_until("DB outage backlog", lambda: pending() >= 3)
            assert status().get("accepted", 0) == prior
        finally:
            compose("up", "-d", "--wait", "db")
        wait_until("DB backlog drained", lambda: not pending())
        compose("stop", "simulator")
        oneshot("simulator.recovery", "drain")
        receipt = json.loads(oneshot("simulator.test_lost_receipt"))
        identifier = receipt["reading_id"]
        effects = database(f"""SELECT count(DISTINCT r.id),count(DISTINCT a.id),count(e.id)
            FROM readings r JOIN assessments a ON a.reading_id=r.id
            JOIN alert_events e ON e.assessment_id=a.id WHERE r.id='{identifier}'""")
        assert effects == "1|1|1", effects
        all_ids = database("SELECT id FROM readings ORDER BY id")
        assert all_ids
        verified = oneshot("simulator.recovery", "verify", "--require-drained", stdin=all_ids + "\n")
        print(f"Lost receipt {identifier}: one reading, one assessment, one alert event.\n{verified}", flush=True)
        # An unregistered device produces a real 422; the valid frame behind it must drain.
        generate_fixture = """import os
from contextlib import closing
from datetime import datetime,UTC
from pathlib import Path
from uuid import uuid4
from simulator.buffer import DEVICE_IDS,connect,generate
with closing(connect(Path(os.environ['BUFFER_PATH']))) as conn:
    for device in DEVICES:
        generate(conn,device,datetime.now(UTC))"""
        def generate_only(devices):
            compose("run", "--rm", "-T", "--no-deps", "simulator", "python", "-",
                    stdin=generate_fixture.replace("in DEVICES:", f"in {devices}:"))
        generate_only("[uuid4(), DEVICE_IDS[1]]")
        oneshot("simulator.recovery", "drain")
        generate_only("[DEVICE_IDS[2]]")
        all_ids = database("SELECT id FROM readings ORDER BY id")
        mixed = json.loads(oneshot("simulator.recovery", "verify", stdin=all_ids + "\n"))
        assert mixed["ok"] and mixed["pending"] == mixed["quarantined"] == 1
        print(f"Retained mixed-status fixture: {mixed}", flush=True)
    finally:
        compose("stop")
        print(f"Preserved evidence in {project} volumes.", flush=True)


if __name__ == "__main__":
    main()
