# Operation Ward Zero

M0 provides a local React environment screen, a FastAPI service and a persistent PostgreSQL database. The screen polls service readiness every 15 seconds. The synthetic patient monitoring workflow starts in M1.

## Start the environment

Use PowerShell from the repository root with Docker Desktop running in Linux container mode. The first build needs network access. Docker supplies Python and Node.

```powershell
# Create the local password once. Reuse this file with the same database volume.
if (!(Test-Path -LiteralPath .env)) {
    Set-Content -Encoding ascii -LiteralPath .env -Value ('POSTGRES_PASSWORD=' + [guid]::NewGuid().ToString('N'))
}
docker compose config -q
docker compose up --build --wait --wait-timeout 120
docker compose ps
```

Open the [environment screen](http://127.0.0.1:8010/) and look for **Service ready**. To select another loopback port, set `APP_PORT` in `.env`. PostgreSQL is accessible inside the Compose network. The app applies Alembic migrations before starting one Uvicorn worker. The M0 revision records the baseline in `alembic_version`.

Use `docker compose down` to stop the environment and retain the named database volume. Start it again with the same `up` command. Keep the generated `.env` private.

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
