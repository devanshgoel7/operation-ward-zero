# Demonstration and verification

Use synthetic data only. Thresholds and 30/60-second response deadlines are demonstration settings. The two caregiver selections provide demo attribution, and all alerts stay in the application.

## Prerequisites and startup

Use Docker Desktop in Linux container mode or Docker Engine with the Compose v2 plugin on Linux. Docker installs the application dependencies from their lockfiles.

From the repository root, copy [`.env.example`](../.env.example) to `.env` for a fresh installation. Set `POSTGRES_PASSWORD` and `SIMULATOR_KEY` to separate private values. In PowerShell, `[guid]::NewGuid().ToString('N')` generates one value per invocation. Reuse the original `.env` with an existing PostgreSQL volume.

```sh
docker compose config -q
docker compose up -d --build --wait --wait-timeout 120
docker compose ps
```

Open the [dashboard](http://127.0.0.1:8010/) using `APP_PORT` if you changed it. The first build needs network access. Use `docker compose down` for an ordinary stop to retain both named volumes.

The full verification needs host Python 3.11+, Node.js with npm, Playwright 1.62.1, Microsoft Edge, and FFmpeg with libx264 on PATH. Use `python3` for host commands if that is how Python is installed. Install Edge separately. Use one of the following blocks to install Playwright outside the repository and make it available to the current shell.

```powershell
$toolDirectory = Join-Path ([System.IO.Path]::GetTempPath()) 'wardzero-browser-tools'
npm install --prefix $toolDirectory playwright@1.62.1
$env:NODE_PATH = Join-Path $toolDirectory 'node_modules'
```

```sh
tool_directory=$(mktemp -d)
npm install --prefix "$tool_directory" playwright@1.62.1
export NODE_PATH="$tool_directory/node_modules"
```

Verify the host tools before running the full suite.

```powershell
python --version
node --version
docker compose version
node -e "console.log(require('playwright/package.json').version)"
ffmpeg -version
```

## Full acceptance command

From the root of a Git checkout with a working `.env`:

```powershell
python scripts/test-acceptance.py
```

The runner creates a unique Compose project and fresh volumes on a random loopback port. It runs fresh startup, the full real-PostgreSQL suite, simulator tests, frontend production build and strict typecheck, responsive dashboard/quality tests, the real failure matrix, context/lifecycle/realtime browser tests, and two complete demo rehearsals. It checks local documentation links and whitespace. It stops at the first failure and writes `acceptance.json` plus one log per check to the printed `artifacts/m7/<timestamp>` directory. A partial report is not a passing report. All evidence volumes remain available; the regular demo project is untouched.

The two demo rehearsals each include a 60-second continuous monitoring check, sampling all three patients at five-second intervals, and an exact saved-alert comparison after a real application restart. Readiness, advancing reading IDs, fresh data and delivery counts are checked during the continuous run. This is a short demonstration check, not a load/endurance benchmark.

## Nine-step recorded demo

To run just the demo in another fresh isolated project:

```powershell
node scripts/test-demo-ui.cjs artifacts/m7/manual-demo
```

Choose a new output directory each time. The script automates real browser actions and records a silent MP4 from timestamped browser screenshots (approximately one captured frame per second, encoded at 10 fps). `demo.json` records steps, IDs and exact reconciliation results. The video preserves elapsed time, including pauses during container commands. It is an automated backup walkthrough, without narration. Screenshots and the recording are local artifacts excluded from Git and Docker build contexts.

1. Show three stable patients. The fixture first seeds two minutes of synthetic stable history through the simulator's durable SQLite buffer and normal uploader, then samples continuously for at least 60 seconds. Seeded observation timestamps are explicit fixture history; response deadlines and outages use real elapsed time.
2. Select persistent deterioration for Mira: SpO2 99 → 96 and heart rate 70 → 90. Wait for supported adjacent-window findings. Record breathlessness through the browser form.
3. Inspect the combination High explanation and its stored reading UUIDs and caregiver observation.
4. Leave the primary alert unanswered. Observe the actual saved deadline escalate to Backup caregiver within the five-second worker interval.
5. Select Backup caregiver and acknowledge in the browser. Confirm saved status and history.
6. Disconnect the simulator container from its real Compose network. Sampling continues in SQLite. Wait for at least 18 pending frames and visible stale patients.
7. Reconnect. Wait for backlog drain and verify that earlier alert events remain unchanged.
8. Stop generation, drain uploads and compare all simulator and PostgreSQL reading IDs. Require empty discrepancy, pending and quarantine sets.
9. Restart sampling, select recovery, clear breathlessness, wait for three fresh complete readings without firing rules, enter a note and resolve as Backup caregiver. Restart the application; verify exact resolved state/history and reconcile IDs again.

The script uses actual service/network operations. It does not change lifecycle deadlines or write directly into PostgreSQL. The broader acceptance tests separately exercise controlled clocks, dropped committed receipts, PostgreSQL failure, simulator restart, replay, historical input, incomplete data, browser disconnection and competing lifecycle commands.

## Manual scenario controls

For a live walkthrough with clean data, start a new Compose project from the configured checkout. The random loopback port lets the regular dashboard on port 8010 keep running. To use port 8010 for the walkthrough, free that port first and set `APP_PORT` to `8010` instead.

```powershell
$demoProject = 'wardzero-judge-demo'
$env:APP_PORT = '0'
docker compose -p $demoProject up -d --build --wait --wait-timeout 120
docker compose -p $demoProject port app 8000
```

Open the printed address in a browser. Choose a new project name for a clean repeat. Select `stable` and allow two minutes of fresh readings before the trend demonstration. Follow the [nine-step walkthrough](#nine-step-recorded-demo) using these controls.

```powershell
docker compose -p $demoProject exec -T simulator python -m simulator.scenario mira stable
docker compose -p $demoProject exec -T simulator python -m simulator.scenario mira deterioration
docker compose -p $demoProject exec -T simulator python -m simulator.scenario mira recovery
docker compose -p $demoProject exec -T simulator python -m simulator.scenario mira missing
docker compose -p $demoProject exec -T simulator python -m simulator.recovery status
```

Patients are `mira`, `aryan`, and `lena`. A selection persists in SQLite across simulator restart and affects subsequent committed frames. Stable/recovery uses heart rate 70 and SpO2 99; deterioration uses 90 and 96, so sustained prior stable history is necessary for trends. Missing sets SpO2 null while other measurements continue. Selecting a scenario cancels that patient's short `trigger_alert` sequence. The older `trigger_alert` command clears the persistent selection and still runs its six-reading sequence before ordinary baseline sampling. No prior reading is edited.

Use the same project's simulator and network for the outage. Leave it disconnected for about 35 seconds so the dashboard can show staleness and the queue can grow. Run the status command while it is still disconnected, then reconnect.

```powershell
$simulatorContainer = docker compose -p $demoProject ps -q simulator
docker network disconnect "${demoProject}_default" $simulatorContainer
docker compose -p $demoProject exec -T simulator python -m simulator.recovery status
docker network connect "${demoProject}_default" $simulatorContainer
```

## Reconcile reading IDs

Use the same isolated project from the manual network disconnection steps. This check assumes the simulator is the only source of readings in that project. Stop generation before draining the buffer so the ID sets stay fixed during the comparison.

```powershell
docker compose -p $demoProject stop simulator
if ($LASTEXITCODE -ne 0) { throw 'Could not stop simulator sampling.' }
try {
    docker compose -p $demoProject run --rm -T --no-deps simulator python -m simulator.recovery drain
    if ($LASTEXITCODE -ne 0) { throw 'Could not drain the simulator buffer.' }
    $serverIds = docker compose -p $demoProject exec -T db psql -v ON_ERROR_STOP=1 -U wardzero -Atc 'SELECT id FROM readings'
    if ($LASTEXITCODE -ne 0) { throw 'Could not read server IDs.' }
    $serverIds | docker compose -p $demoProject run --rm -T --no-deps simulator python -m simulator.recovery verify --require-drained
    if ($LASTEXITCODE -ne 0) { throw 'Reading ID reconciliation failed.' }
} finally {
    docker compose -p $demoProject start simulator
}
```

A passing check has an empty pending set, quarantine set, and all ID discrepancy sets.

After the simulator resumes, select `mira recovery`, clear the breathlessness observation, and wait for three fresh, complete readings without a firing rule. As Backup caregiver, add a resolution note and resolve the episode. Then run `docker compose -p $demoProject restart app`. Once **Service ready** returns, select Backup caregiver and reopen the resolved episode to show the saved note and event history.

## Evidence, submission and reset

Keep the acceptance report, per-check logs, both `demo.json` files, and both MP4 recordings together. Passed evidence must identify the source snapshot used. In a Git checkout, `python scripts/package-submission.py` creates an untagged source ZIP and SHA-256 manifest under `artifacts/submission/`. It includes tracked and eligible untracked source files and the `.env.example` template. Private `.env` values, Git internals, dependencies, local buffers, and raw evidence stay outside the archive. Extract to a new directory and follow the [startup instructions](#prerequisites-and-startup) to run the app. The full acceptance runner also checks the Git diff and packages the working tree, so run it from a checkout.

The archive describes a working-tree snapshot with a base commit and per-file hashes. The [verification record](IMPLEMENTATION_PLAN.md) tracks source publication and tagging separately.

The run reports name the isolated projects. Start a retained fixture with `docker compose -p <exact-project> up -d --wait` and rediscover its port with `docker compose -p <exact-project> port app 8000` (set `APP_PORT=0` to avoid the regular demo port). To stop it and retain evidence, use `docker compose -p <exact-project> down`. Only when you deliberately intend to erase that specific fixture's PostgreSQL and SQLite evidence, run `docker compose -p <exact-project> down --volumes`. Never use the regular project name for a disposable reset.

## Known limits

- Local synthetic prototype only: three adult patients, two demo caregivers, one application worker and one five-second loop.
- No production authentication, external delivery, hardware, multi-organization support, ML, LLM interpretation or validated clinical prediction.
- Persistence assumes intact named volumes and available storage. Pending/quarantined frames require inspection; no automatic data deletion is performed.
- A WebSocket hint proves neither durable browser delivery nor human receipt; REST and recorded caregiver actions remain authoritative.
- Historical thresholds are retained for review; full retrospective trend recomputation is not implemented. Current trends require sufficient continuous per-metric history.
- Recording captures the browser at approximately one frame per second without audio. The 60-second checks are not performance or long-duration reliability certification.
- Host browser tools are prerequisites rather than application dependencies. Existing non-failing dependency deprecation/build warnings are recorded in the acceptance logs.
