# Operation Ward Zero

The local dashboard shows synthetic vital signs for three fictional adults. Each home monitor samples every five seconds. The simulator commits frames to SQLite before sending them to FastAPI. PostgreSQL stores accepted readings and the dashboard polls for the latest observation every five seconds.

## Project layout

The source layout groups files by responsibility.

```text
backend/
  app/
    main.py                    FastAPI startup, router registration, static shell
    api/health.py              HTTP routes and status codes
    api/monitoring.py          Sensor ingestion, dashboard, patient and history routes
    services/monitoring.py     Transactional ingestion and patient queries
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
  pages/Monitoring.tsx         Polling patient cards
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

The M1 simulator keeps every frame in its named volume, including the original payload, delivery status and attempt metadata. It retries the oldest pending frame with delays of 1, 2, 4, 8 and then 15 seconds. A failed upload stays pending and can hold up newer uploads while sampling continues. Retry classification and quarantine are scheduled for M3. M1 receipts carry a null assessment ID. Assessment and alert behavior starts in M2.

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
| `GET /health/ready` | 200 | `{"status":"ready","database":"available","migrations":"current","worker_last_success_at":null}` |
| `GET /health/ready` | 503 | `status: unready`, `database`, `migrations`, nullable `worker_last_success_at`, UUID `request_id`, and `error` containing `code`, `message`, and `details` |

Readiness queries PostgreSQL on each request and compares its applied heads to the packaged migration scripts. An unavailable database returns `database_unavailable` and migration state `unknown`. An available database with a different revision returns `migrations_pending`. The worker timestamp is null until a milestone introduces periodic work.

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

Python dependencies, including the test runner, are pinned with hashes in `backend/requirements.lock`. The direct requirements are in `backend/requirements.in`. For an intentional update, run `uv pip compile --generate-hashes --no-annotate --output-file requirements.lock requirements.in` from `backend/` using Linux Python 3.13 and uv 0.8.22. Frontend versions are in `frontend/package.json` and `frontend/package-lock.json`. Image builds use `npm ci` and pin the base images by digest.
