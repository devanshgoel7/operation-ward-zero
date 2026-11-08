"""M7 fail-fast acceptance runner. Creates isolated services; preserves evidence volumes."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "m7" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = "wardzero-prem7-" + uuid4().hex[:10]
    env = os.environ | {"APP_PORT": "0"}
    report = {"project": project, "started_at": datetime.now(UTC).isoformat(), "checks": [],
              "git_tag": "pending: user prohibits commits and elected to leave this criterion pending"}

    def save() -> None:
        (output / "acceptance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def run(label: str, command: list[str], timeout: int = 900) -> None:
        logfile = output / (label + ".log")
        print(f"START {label}: {' '.join(command)}", flush=True)
        started = time.monotonic()
        with logfile.open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        report["checks"].append({"name": label, "command": command, "exit_code": result.returncode,
                                 "seconds": round(time.monotonic() - started, 1), "log": logfile.name})
        save()
        if result.returncode:
            raise RuntimeError(f"{label} failed; inspect {logfile}. No later checks ran.")
        print(f"PASS {label}", flush=True)

    compose = ["docker", "compose", "-p", project]
    try:
        for executable in ("docker", "node", "ffmpeg"):
            if not shutil.which(executable):
                raise RuntimeError(f"Missing prerequisite: {executable}")
        run("browser-prerequisites", ["node", "-e", "require('playwright'); require('child_process').execFileSync('ffmpeg',['-version']);"])
        run("source-snapshot", [sys.executable, "scripts/package-submission.py"])
        report["source_snapshot"] = json.loads((output / "source-snapshot.log").read_text(encoding="utf-8"))
        run("compose-config", compose + ["config", "-q"])
        run("fresh-startup", compose + ["up", "--build", "-d", "--wait", "--wait-timeout", "120"])
        base = "http://" + subprocess.check_output(compose + ["port", "app", "8000"], cwd=ROOT, env=env, text=True).strip()
        # Wait for fresh input on all patients before the read-only responsive browser checks.
        deadline = time.monotonic() + 45
        while True:
            with urlopen(base + "/api/v1/dashboard", timeout=8) as response:
                snapshot = json.load(response)
            if len(snapshot["patients"]) == 3 and all(p["data_quality"] == "fresh" for p in snapshot["patients"]):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Fresh startup did not deliver all three patients")
            time.sleep(1)
        run("backend", compose + ["exec", "-T", "app", "python", "-m", "pytest", "-q"])
        run("simulator", compose + ["exec", "-T", "simulator", "python", "-m", "unittest", "discover", "-s", "simulator"])
        run("migration", compose + ["exec", "-T", "app", "alembic", "current"])
        run("frontend-build", ["docker", "build", "--target", "frontend", "-t", project + "-frontend", "."])
        run("frontend-typecheck", ["docker", "run", "--rm", project + "-frontend", "npm", "run", "typecheck"])
        run("dashboard-ui", ["node", "scripts/test-dashboard-ui.cjs", base, str(output)])
        run("quality-ui", ["node", "scripts/test-quality-ui.cjs", project])
        run("failure-matrix", [sys.executable, "scripts/test-recovery.py"])
        for name in ("context", "lifecycle", "realtime"):
            run(name + "-ui", ["node", f"scripts/test-{name}-ui.cjs"])
        for repetition in (1, 2):
            run(f"demo-{repetition}", ["node", "scripts/test-demo-ui.cjs", str(output / f"demo-{repetition}")])
        run("docs", [sys.executable, "scripts/check-docs.py"])
        run("diff", ["git", "diff", "--check"])
        report["verification_passed"] = True
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        subprocess.run(compose + ["down"], cwd=ROOT, env=env, check=True, timeout=120)
        report["finished_at"] = datetime.now(UTC).isoformat()
        save()
        print(f"Evidence: {output}. Services stopped; volumes retained. Git tag remains pending.", flush=True)


if __name__ == "__main__":
    main()
