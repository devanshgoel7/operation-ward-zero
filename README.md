# Operation Ward Zero

The local dashboard shows synthetic vital signs for three fictional adults. Each home monitor samples every five seconds. The simulator commits frames to SQLite before sending them to FastAPI. PostgreSQL stores accepted readings. WebSocket hints refresh the dashboard after commits; REST polling continues every 15 seconds when connected and every five seconds otherwise.

## Project layout

The source layout groups files by responsibility.

```text
backend/
  app/
    main.py                    FastAPI startup, router registration, static shell
    api/health.py              HTTP routes and status codes
    api/monitoring.py          Sensor ingestion, dashboard, patient and history routes
    services/monitoring.py     Transactional ingestion and patient queries
    services/trends.py         Median windows and continuity eligibility
    services/context.py        Active observations and combination findings
    services/observations.py   Transactional capture, replay and expiry
    services/realtime.py       Bounded connection queues and best-effort update hints
    api/realtime.py            WebSocket delivery, heartbeat and cleanup
    models/monitoring.py       Reading validation and monitoring contracts
    services/health.py         Database and migration readiness checks
    models/health.py           Typed health response contracts
    core/database.py           Shared SQLAlchemy engine configuration
  migrations/                  Alembic runner and schema revisions
  tests/                       Backend integration checks
frontend/src/
  main.tsx                     React startup and query provider
  api/health.ts                Readiness request
  api/monitoring.ts            Dashboard request with generated OpenAPI types
  api/Realtime.tsx             Reconnection, REST reconciliation and polling intervals
  pages/Monitoring.tsx         Patient cards and synchronization state
  pages/PatientContext.tsx     History chart, trend evidence and observation form
  pages/EnvironmentStatus.tsx  Environment screen
  styles/global.css            Shell styles
scripts/                       Operational verification
simulator/                     Synthetic sampling, SQLite buffer and retrying upload
docs/                          Architecture, decisions and milestone evidence
```

## Start the environment

Use PowerShell from the repository root with Docker Desktop running in Linux container mode. The first build needs network access. Docker supplies Python and Node.

```powershell
# Create the local password once. Reuse this file with the same database volume.
if (!(Test-Path -LiteralPath .env)) {
    Set-Content -Encoding ascii -LiteralPath .env -Value ('POSTGRES_PASSWORD=' + [guid]::NewGuid().ToString('N'))
}
# Add a private sensor key once, including when upgrading an existing M0 stack.
if (!(Select-String -LiteralPath .env -Pattern '^SIMULATOR_KEY=' -Quiet)) {
    Add-Content -Encoding ascii -LiteralPath .env -Value ('SIMULATOR_KEY=' + [guid]::NewGuid().ToString('N'))
}
docker compose config -q
docker compose up --build --wait --wait-timeout 120
docker compose ps
```

Open the [monitoring dashboard](http://127.0.0.1:8010/) and look for three populated patient cards and **Service ready**. To select another loopback port, set `APP_PORT` in `.env`. PostgreSQL is accessible inside the Compose network. The app applies migrations and seeds before starting one Uvicorn worker.

Use `docker compose down` to stop the environment and retain both named volumes. Start it again with the same `up` command. Keep the generated `.env` private.

## M1 monitoring contracts

The [running OpenAPI contract](http://127.0.0.1:8010/docs) lists fields, units and response schemas.

| Request | Behavior |
|---|---|
| `POST /api/v1/readings` | Requires `X-Simulator-Key`. Returns 201 after commit, or 200 with the original receipt timestamp for an identical retry. Conflicting UUID or device sequence returns 409. Invalid measurements or an unknown device return 422. |
| `GET /api/v1/dashboard` | Returns server time, the two caregivers, and three patients with their latest readings. A patient awaiting a first reading has a null latest reading. |
| `GET /api/v1/patients/{patient_id}` | Returns the registered patient, device and latest reading by observation time. |
| `GET /api/v1/patients/{patient_id}/readings` | Returns newest-first history. Use timezone-aware `from` and `to`, a `limit` (default 500, maximum 2,000) and the returned `next_cursor`. The default interval is the last 30 minutes. |

The simulator keeps every frame in its named volume, including its original payload, delivery status and attempt metadata. Sampling continues while the oldest pending upload retries. Network errors, unconfirmed receipts, HTTP 408, 429 and server errors back off with jitter up to 15 seconds. A longer Retry-After takes precedence. Other 4xx responses quarantine that frame and allow the next upload to proceed.

## Verify M6

M6 adds live update hints and dashboard usability improvements to the existing monitoring and caregiver workflows. Start or upgrade with `docker compose up --build --wait --wait-timeout 120`. No migration was added; the head remains `0008_resolution`. Existing volumes and evidence are preserved.

On the [dashboard](http://127.0.0.1:8010/), **Live updates connected** indicates the WebSocket transport is available. The banner separately shows the last successful REST refresh. Connections and reconnections reload saved dashboard, selected history and visible alert queries. WebSocket messages contain only invalidation hints, never authoritative patient state or proof of caregiver acknowledgement. Polling remains active at 15 seconds when connected and five seconds otherwise. Silent connections are detected after 25 seconds without a valid message; reconnection backs off from one to 15 seconds. REST requests time out after eight seconds.

If refreshing fails, cards and panels identify cached, unverified state. The server continues to distinguish fresh, incomplete, stale and unavailable patient data. **Refresh now** retries the dashboard query. An unconfirmed acknowledgement, observation or resolution retains its original command/payload through reload in session storage. Select the same caregiver and patient, and use the saved retry action; a possibly committed action is never undone by a discarded draft. The resolved-alert list also preserves access to unconfirmed resolution retries.

Use Tab to reach the skip link, selectors, buttons, notes and evidence/history disclosures, and Enter/Space to activate native controls. The history chart includes metric units, a textual latest value/range, visible individual points for single readings, and line breaks for missing measurements and gaps. The layout is verified at 1366×768.

| Interface | M6 behavior |
|---|---|
| `WS /api/v1/ws` | Emits `patient.updated`, `alert.updated`, `system.status` and ten-second `heartbeat` messages with `server_time` and optional patient/alert IDs and revision. Hints follow transaction commit. |
| Connection delivery | Each client has a 32-message outbound queue. Queue overflow or a three-second blocked send disconnects that client; ingestion never awaits a socket. REST reconciliation/polling recovers missed hints. |

```powershell
docker compose exec -T app python -m pytest -q
docker compose exec -T simulator python -m unittest discover -s simulator
docker compose exec -T app alembic current
# Requires Node, Playwright and Microsoft Edge, as with the M4/M5 scripts.
node scripts/test-realtime-ui.cjs
node scripts/test-context-ui.cjs
node scripts/test-lifecycle-ui.cjs
```

The M6 browser script creates its own Compose project, PostgreSQL volume and random loopback ports. A real TCP proxy cuts browser connections while the backend saves an alert, then restores transport to verify reconciliation. It also blocks only WebSockets to verify polling, pauses socket forwarding to verify heartbeat-loss detection, and restarts the real app. It checks commit-to-render timing, retained mutation payloads, a lost committed acknowledgement response, real staleness, keyboard actions and rendered chart dimensions. It saves `m6-browser-evidence.png` and `m6-disconnected-recovery-evidence.png`, stops the fixture services and retains the evidence volume. It does not alter the regular demo data. The regular build includes strict TypeScript and the production bundle check.

## Verify M5

M5 completes caregiver escalation and resolution. Upgrade with `docker compose up --build --wait --wait-timeout 120`; migration `0008_resolution` preserves existing evidence, assignments, deadlines and command IDs. Existing episodes start with zero counted recovery readings and collect new evidence after upgrade.

On the [dashboard](http://127.0.0.1:8010/), select Alex Morgan and trigger a synthetic episode:

```powershell
docker compose exec -T simulator python -m simulator.trigger_alert mira
```

Leave it unanswered. The inbox displays the saved deadline: Watch allows 60 seconds; High shortens the remaining wait to at most 30 seconds. The five-second worker assigns it to backup Sam Rivera once. Select Sam and **Acknowledge**. Acknowledgement cancels the deadline. Backup alerts remain visibly unacknowledged until acted on; there is no third tier. New concern after recovery or a rise to High reopens an acknowledged episode under Alex and retains earlier responses in history.

Wait for **Recovery: 3/3**. Risk resolution requires three consecutive new current, fresh, complete readings with no threshold, trend or active observation findings. Incomplete data, firing rules or a freshness break reset recovery. Historical input and repeated uploads do not count. Clearing or expiring observations cannot create recovered readings. Add a required resolution note (maximum 500 characters), then **Resolve alert**. The server rejects premature or stale recovery. Delayed-review episodes need acknowledgement and a review note; monitoring gaps continue to close automatically after three fresh complete readings.

Expand **Lifecycle history** for actors, transition times, the resolution note and acknowledgement response durations. Response time runs from the latest opening/reopening; assignment response time runs from that point or the latest backup handoff. **Show recently resolved alerts** displays the newest 50 resolved episodes for the selected caregiver; the paginated alerts API retains all episodes. Notes are displayed literally. Unconfirmed resolution commands and notes survive reload in session storage; select the same caregiver and use **Retry saved resolution**, including from the resolved list when the original save succeeded. Discarding a draft never undoes a saved resolution.

| Request | M5 behavior |
|---|---|
| `POST /api/v1/alerts/{id}/resolve` | Requires current assignee in `X-Demo-Caregiver-Id` and body `{ "command_id": "UUID", "note": "Recovery/review note" }`. Returns updated alert after commit. Identical replay returns 200 without another transition; conflicting command/note or unmet conditions returns 409, wrong actor 403, invalid note 422, persistence failure 503. |
| `GET /api/v1/alerts/{id}` | Saved events now include response durations and resolution notes in `details`. Alert fields include saved deadline, current-cycle escalation/response timestamps, recovery count/last observation, resolution time and actor. |
| `POST /api/v1/alerts/{id}/acknowledge` | Exact retries remain safe after subsequent reassignment or reopening and return current state without acknowledging a new response cycle. A new cycle needs a new command. |

```powershell
docker compose exec -T app python -m pytest -q
docker compose exec -T simulator python -m unittest discover -s simulator
docker compose exec -T app alembic current
# Requires Node, Playwright and Microsoft Edge, as with the M4 check.
node scripts/test-lifecycle-ui.cjs
node scripts/test-context-ui.cjs
```

The M5 browser script creates its own Compose project on a random loopback port. It measures a real 30-second primary timeout against the five-second loop, acknowledges as backup, verifies rejected premature resolution and retained drafts, supplies recovery, drops a committed resolution response and retries it, then checks saved history across real app stop/start and restart. It makes a separate fixture's deadline overdue while the app is stopped and verifies one escalation across two starts. It saves `m5-browser-evidence.png`, stops its services and preserves its PostgreSQL evidence volume. The regular demo data is untouched by these fixtures. Backend tests use disposable real PostgreSQL databases and controlled times for boundaries, races, idempotency, rollback and M4 migration compatibility.

## Verify M4

M4 adds observed-time history charts, two descriptive trends, and caregiver observations. Start or upgrade with the normal `docker compose up --build --wait --wait-timeout 120` command; existing volumes and receipts are preserved. M4 introduced migration `0007_context`; the current M5 head is `0008_resolution`.

On the [dashboard](http://127.0.0.1:8010/), select **Demo caregiver**, then use **History and observations** to select a patient and chart metric. The chart shows the last 30 minutes, breaks lines at missing measurements or gaps over ten seconds, and reports its 2,000-row display limit when relevant. Trend summaries show counts, window times, medians/change, or why continuous history is insufficient. Findings expand to the exact stored reading evidence.

Use **Record observation** for breathlessness, dizziness, or reduced intake. **Present** applies for ten minutes; **Absent / clear this tag** immediately removes that tag. Only the patient's seeded primary or backup caregiver may submit. Notes (maximum 500 characters) are stored and displayed literally. An active tag floors concern at Watch; breathlessness plus a current SpO₂ threshold breach or supported falling trend raises High. Clearing or expiry preserves other firing rules and the alert's peak priority. Risk resolution follows the [M5 conditions](#verify-m5).

Failed or unconfirmed saves retain the exact payload and UUID through reload. Select the same patient and caregiver, then **Retry saved observation**. **Discard draft** only removes the browser draft; it does not undo a possible server save.

| Request | M4 behavior |
|---|---|
| `POST /api/v1/patients/{id}/observations` | Requires `X-Demo-Caregiver-Id`. Body: `observation_id` UUID, `tag`, strict boolean `present`, optional `note`. Returns observation and assessment after commit: 201 new, 200 identical replay, 409 conflicting UUID, 403 unassigned actor, 422 invalid fields, 503 persistence failure. Creation and expiry times are server-assigned. |
| `GET /api/v1/patients/{id}` and `GET /api/v1/dashboard` | Include active observations and contextual assessment findings/trend summaries. Reading-triggered assessment IDs remain stable on ingestion replay. |

The trend windows are `(t−120s,t−60s]` and `(t−60s,t]`, anchored to the eligible latest reading. Each metric needs eight non-null samples per window and gaps no larger than ten seconds, including the outer edges. Median SpO₂ change ≤−3 percentage points or heart-rate change ≥20 bpm produces Watch. Historical ingestion remains threshold-only; recovered history can contribute to the next eligible current window. All parameters are synthetic demonstration settings, not clinical validation.

```powershell
docker compose exec -T app python -m pytest -q
docker compose exec -T simulator python -m unittest discover -s simulator
docker compose exec -T app alembic current
# Requires Node, Playwright, and Microsoft Edge, as with the M3 browser check.
node scripts/test-context-ui.cjs
```

The M4 browser script builds a uniquely named isolated Compose project with a random loopback port, submits 24 stored readings, verifies both trends and the chart, records breathlessness to produce High, clears it, and drops a real committed observation response before retrying after reload. It also stops the real app, makes an observation overdue in that isolated fixture, and verifies startup expiry. It saves `m4-browser-evidence.png` (ignored by Git), stops its services, and retains its PostgreSQL evidence volume. It never changes the regular demo dataset. The backend suite uses disposable real PostgreSQL databases and controlled evaluation times for exact expiry/window boundaries, replay/concurrency, rollback, and migration compatibility.

## Verify M3

From the repository root, with Docker Desktop running and the local environment configured, run the following checks. The failure matrix uses host Python 3.11+ and Docker Compose. It creates its own project and loopback port, stops its services afterward, and prints the project name so you can inspect its volumes.

```powershell
python scripts/test-recovery.py
docker compose exec -T app python -m pytest -q
docker compose exec -T simulator python -m unittest discover -s simulator
docker compose exec -T simulator python -m simulator.recovery status
```

The matrix disconnects the simulator from its Docker network, stops the app, restarts the simulator during that outage, and stops PostgreSQL. A local HTTP proxy receives a real committed response from FastAPI and closes its downstream connection before delivering it. The test checks the retried reading, assessment and audit event in PostgreSQL.

For a manual ID comparison on a simulator-only dataset, freeze sampling first. The verifier reads every server UUID on stdin and reports missing, unexpected and overlapping IDs. The strict check requires every generated frame to be accepted. Omit `--require-drained` to inspect a mixed pending/quarantined fixture. Run `status` for retained error reasons and retry times.

```powershell
docker compose stop simulator
docker compose run --rm -T --no-deps simulator python -m simulator.recovery drain
$serverIds = docker compose exec -T db psql -v ON_ERROR_STOP=1 -U wardzero -Atc 'SELECT id FROM readings'
if ($LASTEXITCODE -ne 0) { throw 'Could not read server IDs.' }
$serverIds | docker compose run --rm -T --no-deps simulator python -m simulator.recovery verify --require-drained
docker compose start simulator
```

On the dashboard, a delivery over ten seconds late is labelled. After 30 seconds without a complete observation the worker opens one monitoring gap. Three consecutive fresh complete frames close it. The card shows the last known concern and observation time when assessment is unavailable. A recent incomplete reading can still raise high concern. Historical breaches accumulate in a separate delayed-review episode with their original observation times.

For the browser regression, use Node with Playwright and Microsoft Edge available. Start a separate populated QA stack with `$env:APP_PORT='18013'; docker compose -p wardzero-m3-check up --build -d --wait`, then run `node scripts/test-quality-ui.cjs wardzero-m3-check`. This fixture pauses and restores its simulator and writes synthetic readings directly through the ingestion API. Use the recovery matrix's separate dataset for exact simulator-ID comparisons.

## Verify M2

Run `docker compose exec -T app python -m pytest -q` against the started stack. For the live presentation, open the [monitoring dashboard](http://127.0.0.1:8010/) and leave it open. From the repository root, run:

```powershell
docker compose exec -T simulator python -m simulator.trigger_alert
```

On Mira's next three samples her simulated SpO₂ is 93% (Watch), followed by three at 88% (High). Each phase lasts about 15 seconds. The usual uploader sends each saved frame and the dashboard refreshes through live hints with polling fallback. Show the latest alert evidence, then acknowledge as Alex Morgan. Sampling returns to baseline automatically, while the alert retains its peak and acknowledgement history.

Without an argument, successive commands rotate through Mira, Aryan, Lena, then Mira again. The simulator saves the next patient in SQLite. Pass `mira`, `aryan`, or `lena` to target a patient explicitly. Each successful trigger advances to the following patient.

To show escalation, leave Alex's alert unanswered. Watch allows 60 seconds. High shortens the remaining wait to at most 30 seconds. With this scenario Sam typically takes over about 45–50 seconds after the first Watch reading. Select Sam in the caregiver dropdown to acknowledge. Acknowledging cancels the deadline. New concern after a complete baseline reading, or a rise from Watch to High, reopens an acknowledged episode under Alex and preserves the previous response in history.

### Optional isolated M2 fixture

To inspect a pre-seeded episode separately, run:

```powershell
.\scripts\start-alert-demo.ps1
```

The script starts the separate `wardzero-m2-demo` Compose project on loopback port 8012 and posts two synthetic readings through the sensor API. Its database is separate from the regular simulator and patient history. To use another port, pass `-Port`.

1. Open the [M2 dashboard](http://127.0.0.1:8012/). Mira Shah's risk alert shows SpO₂ of 88%, the high threshold of <90%, the reading ID, and observation time. The missing temperature appears as incomplete data.
2. Expand **Opening evidence** to see the earlier 93% reading that crossed the watch threshold of <94%.
3. Select Alex Morgan in **Caregiver inbox** to see the alert while it is assigned to him. After escalation, select Sam Rivera to see it in his inbox. Click **Acknowledge** as the current assignee and reload to see the saved actor and time.

Rerunning the script reuses the saved episode. Stop the isolated environment with `docker compose -p wardzero-m2-demo down`. To deliberately **erase only the M2 demo data** for a fresh walkthrough, use `docker compose -p wardzero-m2-demo down --volumes` and rerun the script.

### M2 contracts

- New reading receipts include the assessment ID after the database commits. Identical retries return that same ID. Replays of readings originally stored by M1 retain their original receipt time and null assessment ID.
- The dashboard includes current assessments and active risk alerts. Each alert retains its opening assessment, latest triggering assessment, and peak priority. Findings include the demo rule ID/version, measurement, unit, condition, reading ID, and observation time. A partial reading with a breach can trigger an alert. A partial reading without a breach has null concern.
- `GET /api/v1/alerts` supports patient, assignee and status filters, plus cursor pagination. `GET /api/v1/alerts/{id}` adds chronological events. `POST /api/v1/alerts/{id}/acknowledge` accepts a UUID `command_id` and an `X-Demo-Caregiver-Id` header. Retrying the same command returns the stored alert with one acknowledgement event. Another caregiver receives 403. Reusing the command for another alert or sending a new command to an acknowledged alert returns 409.

## Verify M1

Run these commands against the started stack. Backend integration tests migrate a temporary database on the Compose PostgreSQL service. The browser check needs Microsoft Edge and restarts the app. It compares the IDs on all three rendered cards with the SQLite payloads and the PostgreSQL-backed history before and after restart.

```powershell
docker compose exec -T app python -m pytest -q
docker compose exec -T simulator python -m unittest simulator.test_buffer
docker compose exec -T app alembic current
.\scripts\test-monitoring.ps1
```

To regenerate the checked-in frontend types when the API changes, run the following from the repository root with a running app and Node/npm available.

```powershell
npx --yes openapi-typescript@7.10.1 http://127.0.0.1:8010/openapi.json -o frontend/src/api/schema.d.ts
```

## M0 contracts

Both health routes take a GET request with no body or credentials. The running service publishes its response schemas in [OpenAPI](http://127.0.0.1:8010/openapi.json).

| Request | HTTP | Response |
|---|---|---|
| `GET /health/live` | 200 | `{"status":"live"}` while the process can serve requests |
| `GET /health/ready` | 200 | `{"status":"ready","database":"available","migrations":"current","worker_last_success_at":"<UTC timestamp>"}` |
| `GET /health/ready` | 503 | `status: unready`, `database`, `migrations`, nullable `worker_last_success_at`, UUID `request_id`, and `error` containing `code`, `message`, and `details` |

Readiness queries PostgreSQL on each request and compares its applied heads to the packaged migration scripts. An unavailable database returns `database_unavailable` and migration state `unknown`. An available database with a different revision returns `migrations_pending`. The worker checks freshness and saved deadlines at startup and every five seconds. Readiness returns 503 with `worker_overdue` when its last successful pass is over 15 seconds old.

The planned reading, assessment and alert request/response contracts are in the [architecture](docs/ARCHITECTURE.md#public-interfaces). The [implementation plan](docs/IMPLEMENTATION_PLAN.md) tracks when each becomes available.

## Verify M0

With the app running, execute:

```powershell
docker compose exec -T app python -c "from app.main import app; print(app.title)"
docker compose exec -T app python -m pytest -q
docker compose exec -T app alembic current
docker build --target frontend -t wardzero-m0-frontend .
docker run --rm wardzero-m0-frontend npm run typecheck
.\scripts\test-readiness.ps1
```

The frontend stage also runs the production build. The readiness script stops only this project's PostgreSQL service, checks that liveness stays at 200 and readiness returns 503, then restores the database and checks for 200. To check the browser, open the environment screen and verify the heading **Environment status** and the live text **Service ready**.

Python dependencies, including the test runner, are pinned with hashes in `backend/requirements.lock`. The direct requirements are in `backend/requirements.txt`. For an intentional update, run `uv pip compile --generate-hashes --no-annotate --output-file requirements.lock requirements.txt` from `backend/` using Linux Python 3.13 and uv 0.8.22. M6 adds only `wsproto==1.3.2`, with its published wheel/source hashes; the container build verifies hashes and runs `pip check`. Frontend versions are in `frontend/package.json` and `frontend/package-lock.json`. Image builds use `npm ci` and pin the base images by digest.
