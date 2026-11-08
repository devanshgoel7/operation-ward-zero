# Operation Ward Zero

Operation Ward Zero is a local prototype for home health monitoring and caregiver response. It tracks vital signs for three fictional adults, shows the evidence behind each concern, and records caregiver actions. The simulator keeps sampling during a network interruption and uploads the saved readings when the connection returns.

Use synthetic data only. The rules and response deadlines are demonstration settings. The caregiver selector records demo attribution.

## Features

- Live patient roster with heart rate, oxygen saturation, blood pressure, temperature, and separate reading quality indicators.
- Observed-time history, two descriptive trends, and structured caregiver observations. Saved findings identify the measurements and observations that triggered a rule.
- In-app caregiver inbox with acknowledgement, primary-to-backup escalation, recovery progress, resolution notes, and lifecycle history.
- Persistent SQLite buffering, idempotent ingestion into PostgreSQL, and exact reading ID reconciliation after a real outage.
- WebSocket update hints, REST reconciliation, polling fallback, and a service readiness panel.

## Prerequisites

Use Docker Desktop in Linux container mode, or Docker Engine with the Compose v2 plugin on Linux. The first build needs network access to pull images and install locked dependencies. Docker supplies the application runtimes. The full browser verification has separate [host tool prerequisites](docs/DEMO_RUNBOOK.md#prerequisites-and-startup).

## Quick start

Clone the repository and enter its root.

```sh
git clone https://github.com/devanshgoel7/operation-ward-zero.git
cd operation-ward-zero
```

On a fresh installation, copy [`.env.example`](.env.example) to `.env` and fill in `POSTGRES_PASSWORD` and `SIMULATOR_KEY` with two distinct private values. Keep the existing `.env` when reusing a PostgreSQL volume. On Windows, this PowerShell block generates the file for you.

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    $postgresPassword = [guid]::NewGuid().ToString('N')
    $simulatorKey = [guid]::NewGuid().ToString('N')
    Get-Content -LiteralPath .env.example | ForEach-Object {
        $line = $_ -replace '^POSTGRES_PASSWORD=$', "POSTGRES_PASSWORD=$postgresPassword"
        $line -replace '^SIMULATOR_KEY=$', "SIMULATOR_KEY=$simulatorKey"
    } | Set-Content -Encoding ascii -LiteralPath .env
}
```

Start the application, database, and simulator from the repository root.

```sh
docker compose config -q
docker compose up -d --build --wait --wait-timeout 120
docker compose ps
```

Open the [dashboard](http://127.0.0.1:8010/). Look for three populated patient rows and **Service ready** under **System health**. Select **Review patient** to inspect the chart and observation form. Use the top-bar caregiver selector to switch between **Primary caregiver** and **Backup caregiver**.

The app runs migrations before starting FastAPI and serves the built React dashboard on the same port. See the running [interactive OpenAPI reference](http://127.0.0.1:8010/docs) and [readiness response](http://127.0.0.1:8010/health/ready). Adjust the port in these URLs if you change `APP_PORT`.

## Configuration

The [environment template](.env.example) lists the Compose settings used by the quick start.

| Setting | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | Required private password for the internal PostgreSQL service. Reuse the original value with an existing volume. |
| `SIMULATOR_KEY` | Required private key shared by the simulator and ingestion API. |
| `APP_PORT` | Optional host port. Defaults to 8010 and binds to `127.0.0.1`. |

Keep `.env` private. Compose maintains separate `postgres_data` and `simulator_data` named volumes. To stop the stack and retain both volumes, run:

```powershell
docker compose down
```

## Try a synthetic scenario

Trigger a short threshold breach on Mira to see a saved alert and its evidence in the caregiver inbox:

```powershell
docker compose exec -T simulator python -m simulator.trigger_alert mira
```

The simulator also supports persistent `stable`, `deterioration`, `recovery`, and `missing` scenarios for `mira`, `aryan`, and `lena`. For example, select `deterioration` to generate a sustained change in heart rate and oxygen saturation:

```powershell
docker compose exec -T simulator python -m simulator.scenario mira deterioration
docker compose exec -T simulator python -m simulator.recovery status
```

For the full judge walkthrough, follow the [demo runbook](docs/DEMO_RUNBOOK.md#nine-step-recorded-demo). It covers both trends, observation entry, escalation to Backup caregiver, a real network cut, exact reading ID reconciliation, and resolution that survives an application restart. With the host tools installed, `node scripts/test-demo-ui.cjs` rehearses the whole workflow in a fresh Compose project and saves a recording and a JSON report.

## Dependencies and verification

The Docker build uses Python 3.13, PostgreSQL 17, and Node.js 22 for the frontend build, with base images pinned by digest. The backend installs from [requirements.lock](backend/requirements.lock) with hash verification. The frontend uses `npm ci` and [package-lock.json](frontend/package-lock.json). The simulator uses Python's standard library.

Run the backend and simulator suites against the running Compose stack:

```powershell
docker compose exec -T app python -m pytest -q
docker compose exec -T simulator python -m unittest discover -s simulator
docker compose exec -T app alembic current
```

The expected migration head is `0009_caregiver_labels`. For full acceptance, follow the [host tool setup](docs/DEMO_RUNBOOK.md#prerequisites-and-startup) for Python, Node.js, Playwright, Edge, and FFmpeg. Run `python scripts/test-acceptance.py` from a Git checkout. It uses isolated Compose projects and retains its reports and recordings locally under `artifacts/`.

## Troubleshooting

| Symptom | Check |
|---|---|
| Compose reports a missing password or simulator key | Check the two entries in `.env` against `.env.example`. If the file already belongs to a running or stopped project, preserve its database password. |
| The dashboard port is occupied | Set `APP_PORT` to an available loopback port in `.env` and use that port in the dashboard URL. |
| The service is unready | Inspect `/health/ready` and run `docker compose logs app db` to check database connectivity, migrations, and the periodic worker. |
| Readings are stale or unavailable | Run `docker compose logs simulator` and `docker compose exec -T simulator python -m simulator.recovery status` to inspect sampling and buffered uploads. |

## Project layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI routes, deterministic rules, persistence, Alembic migrations, and integration tests |
| `frontend/` | React dashboard, API types, charts, and caregiver workflows |
| `simulator/` | Synthetic scenarios, durable SQLite buffering, uploader, and recovery commands |
| `scripts/` | Verification, browser rehearsals, and source packaging |
| `docs/` | Technical report, architecture reference, and demo runbook |

Read the [technical documentation](docs/TECHNICAL_DOCUMENTATION.md) for the architecture, rules, alert lifecycle, and recovery evidence.
