# Implementation plan and progress

Updated 2026-11-07. Read [AGENTS.md](../AGENTS.md) before work. The approved behavior is in [ARCHITECTURE.md](ARCHITECTURE.md), with rationale in [DECISIONS.md](DECISIONS.md).

## Current state

M0 through M3 are complete. The simulator retains frames across transport and service outages. PostgreSQL stores assessment evidence, monitoring gaps and delayed-review episodes. The polling dashboard distinguishes current data quality from concern. The [M3 walkthrough](../README.md#verify-m3) reproduces the failure matrix in an isolated project. The user requested an uncommitted M3 handoff.

The workspace was empty when documentation creation began. During planning on 2026-11-05, Python and Node were absent from the inspected shell PATH. Docker CLI was present, its daemon was unreachable, and its user configuration could not be read in that session. Recheck these observations during M0. They do not establish the machine's permanent configuration.

The M0 through M3 sections record executed checks. M4 awaits authorization. The earlier caregiver handoff remains recorded under M5.

## Budget and priorities

The budget is 48 development hours, with 40 planned hours and eight contingency hours. P0 includes monitoring, durable ingestion, threshold rules, data quality, trends, observations, alerts, acknowledgement, escalation, resolution, dashboard, and actual failure recovery. Competitive differentiation comes from depth in these capabilities.

P1, after P0 passes, includes a compact reliability export, connection-gap visualization, and one extra scenario. P2 future work includes ML forecasting, LLM interpretation, attendance, real authentication, external messaging, hardware, hosting, and scaling.

| Milestone | Hours | Cumulative | Status |
|---|---:|---:|---|
| M0 Environment and contracts | 3 | 3 | Complete |
| M1 Durable monitoring vertical slice | 6 | 9 | Complete |
| M2 Explained alerts and acknowledgement | 6 | 15 | Complete |
| M3 Failure recovery and data quality | 7 | 22 | Complete |
| M4 Historical trends and observations | 5 | 27 | Pending |
| M5 Escalation and lifecycle completion | 4 | 31 | Partial — requested caregiver handoff implemented; full lifecycle gate pending |
| M6 Real-time dashboard polish | 5 | 36 | Pending |
| M7 Full verification and submission | 4 | 40 | Pending |
| Contingency | 8 | 48 | Reserved |

## Common completion gate

For each milestone, plan → implement → test → review → commit → next feature. Complete its criteria, relevant regression checks, and documentation updates before proceeding. Record test commands and actual results. A milestone is done when its working demonstration succeeds, its evidence is recorded, and the reviewed feature is committed within the authorized workflow. Preserve compatibility with completed milestones.

### M0 — Environment and contracts

Establish reproducible container development, compatible dependency locks, application entry points, migrations, test commands, and API contracts. Likely areas are Compose, backend/frontend manifests, migration configuration, and documentation. There are no milestone dependencies.

- [x] Docker engine is reachable and required images build.
- [x] Application and PostgreSQL start from documented commands.
- [x] Readiness reflects database availability.
- [x] Frontend builds and renders a shell.
- [x] Initial request/response contracts and test commands are recorded.

Run container build, readiness smoke test, Python import test, and TypeScript check. Demonstrate a browser shell and successful readiness. Done requires the common gate and repeatable setup. Select and lock dependency versions here.

**Verification on 2026-11-06.** Tests ran on Docker Desktop's Linux engine 29.5.3 with Compose v5.1.4, a named PostgreSQL volume and one application worker.

| Check run | Observed result |
|---|---|
| `docker compose config -q` and `docker compose up --build --wait --wait-timeout 120` | Configuration validated. First startup created the volume and both services became healthy. Repeating startup against the existing volume also succeeded. |
| `docker build --target frontend -t wardzero-m0-frontend .` and `docker run --rm wardzero-m0-frontend npm run typecheck` | Production Vite bundle and strict TypeScript check passed. The final build installed the npm lock with zero reported advisories. Backend installation verified package hashes and passed `python -m pip check`. |
| `docker compose exec -T app python -c "from app.main import app; print(app.title)"` | Printed `Operation Ward Zero`. |
| `docker compose exec -T app python -m pytest -q` | 3 passed, covering application import and migration head, live HTTP responses backed by PostgreSQL, and published OpenAPI status contracts. |
| `docker compose exec -T app alembic current` | Reported `0001_environment (head)`. With the empty M0 baseline downgraded via `alembic downgrade base`, readiness returned 503 with `database=available` and `migrations_pending`. Restored with `alembic upgrade head` and reran pytest. All 3 passed. |
| `./scripts/test-readiness.ps1` | Ready 200 before a real database stop. While stopped, live 200 and ready 503 with `database_unavailable` and a request UUID. After database restart, ready 200 with current migrations. |
| Edge `--headless --virtual-time-budget=5000 --dump-dom http://127.0.0.1:8010/` with a fresh profile | Rendered the React heading “Environment status” and the fetched status “Service ready”. |

The [README](../README.md#m0-contracts) records M0 requests, responses and repeatable checks. The existing [planned API contracts](ARCHITECTURE.md#public-interfaces) cover later milestones.

### M1 — Durable monitoring vertical slice

Depends on M0. Implement patient/device/reading storage, seeds, simulator SQLite buffering and basic retries, ingestion, patient queries, and a polling dashboard. Likely areas are simulator generation/buffer/upload, backend models/ingestion, and frontend patient view.

- [x] Generated frames commit locally before upload.
- [x] Frames reach PostgreSQL and appear in the browser.
- [x] Identical retries create one reading.
- [x] Accepted data survives application restart.
- [x] The working single-patient path extends to all three seeded patients.

Test validation, duplicate ingestion, repeatable migrations/seeds, and simulator-payload-to-query integration. Demonstrate actual generated database-backed readings. Done requires the common gate and a working end-to-end monitoring path.

**Verification on 2026-11-06.** The app reused the M0 PostgreSQL volume and health routes. A separate named volume holds simulator frames. All commands ran from the repository root.

| Check run | Observed result |
|---|---|
| `docker compose config -q` and `docker compose up --build --wait --wait-timeout 120` | Configuration passed. TypeScript and the production Vite build passed. All three services started. |
| `docker compose exec -T app alembic current` | Reported `0002_monitoring (head)` on the upgraded M0 database. |
| `docker compose exec -T app python -m pytest -q` | 19 passed, including all three M0 checks. A disposable PostgreSQL database went through upgrade, downgrade to M0, upgrade and a repeated upgrade. Tests exercised both caregivers, all three devices, validation, key enforcement, nullable readings and paginated history. Four concurrent copies produced one 201 and three 200 responses with one stored row. Conflicting payloads, sequences and IDs returned 409. The test client emitted one dependency deprecation warning. |
| `docker compose exec -T simulator python -m unittest simulator.test_buffer` | 1 passed. A separate connection reopened the committed pending frame. A simulated upload failure preserved it, delayed the retry, then resent identical bytes. A matching duplicate receipt marked it accepted. The next generated frame advanced the sequence. |
| `./scripts/test-monitoring.ps1` | Headless Edge rendered real heart rates and reading IDs for Mira Shah (`7edb8f3c-7d28-4b37-9b95-88ff4e3a0727`), Jon Ellis (`7419b5e3-21cb-48f1-8ac1-c5cc369ef771`) and Lena Park (`7ab5e6f6-ef62-42a4-84eb-02bab1a790bc`). For each ID, the accepted SQLite payload matched the patient history query. After a real app restart each ID still appeared once with its original receipt timestamp. |
| `./scripts/test-readiness.ps1` | M0 regression passed. Readiness returned 200 before stopping PostgreSQL, then 503 during the outage while liveness returned 200. Readiness returned 200 after restoring PostgreSQL. |

Commit omitted at the user's request. M1 has no open acceptance items. M2 assessments and the M3 failure matrix remain pending.

### M2 — Explained alerts and acknowledgement

Depends on M1. Implement thresholds, assessments, episodes, events, primary assignment, acknowledgement, and explanation UI. Likely areas are risk, alerts, migrations, and the frontend alert panel.

- [x] Abnormal input creates one explained alert.
- [x] Repeated abnormal readings update the episode.
- [x] Acknowledgement persists and retries safely.
- [x] Failed transactions preserve atomicity across reading and alert effects.
- [x] Incomplete high readings still raise concern.

Test threshold boundaries, mixed priorities, incomplete inputs, rollback, duplicate effects, and command retries. Demonstrate concern → explanation → acknowledgement. Done requires the common gate and the complete basic response workflow.

**Verification on 2026-11-06.** M2 extends the M1 patient lock and transaction. The migration preserves existing readings. Each new reading has one immutable threshold assessment. The newest eligible reading can open or update the patient's risk episode. Late or out-of-order frames receive historical assessments. Delayed-review episodes and periodic freshness checks belong to M3.

| Check run | Observed result |
|---|---|
| `docker compose up --build --wait --wait-timeout 120` and `docker compose exec -T app alembic current` | The populated M1 stack upgraded to `0003_explained_alerts (head)`. Strict TypeScript and the Vite production build passed. All three services started. |
| `docker compose exec -T app python -m pytest -q` | 41 passed, including 18 strict boundary cases, mixed priorities, incomplete inputs, peak and opening evidence, receipt and command retries, and M0/M1 regressions. One existing TestClient dependency deprecation warning. A populated M1 migration fixture replayed successfully with its original receipt time and null assessment ID. |
| PostgreSQL failure and concurrency checks in the same suite | A constraint rejected the final audit insert. Ingestion returned 503 and rolled back the reading, assessment, patient pointers, and alert. Retrying after removing the constraint created one episode. Four concurrent copies of a watch reading created one assessment and one opening event. Three concurrent acknowledgements with one command produced one acknowledgement event. |
| `./scripts/start-alert-demo.ps1` and headless Edge via Playwright | The isolated dashboard displayed Mira Shah's 93% opening SpO₂ and 88% high finding on an incomplete frame. Switching caregivers disabled acknowledgement for Sam Rivera and enabled it for Alex Morgan. Clicking as Alex and reloading showed the saved acknowledgement. |
| `docker compose -p wardzero-m2-demo restart app` and GET alert detail after readiness | Alert `fe4e1547-4772-4629-9500-73dc793fb0d8` retained revision 3, both evidence snapshots, the acknowledgement timestamp and the same three events in order (opened, updated, acknowledged). |
| `docker compose exec -T simulator python -m unittest simulator.test_buffer`, `./scripts/test-monitoring.ps1`, and `./scripts/test-readiness.ps1` | The buffer test passed. All three rendered readings matched SQLite and server history across an app restart. Readiness returned 200 → 503 → 200 across the database stop and restart, with liveness 200 during the outage. |

### M3 — Failure recovery and data quality

Depends on M2. Implement retry classification, quarantine, freshness, historical input handling, gap/review alerts, and verification. Likely areas are simulator upload/verification, ingestion/freshness/health, and quality UI.

- [x] Network interruptions accumulate and subsequently drain persistent readings.
- [x] Simulator restart retains pending records and sequence numbers.
- [x] Application and database outages produce no false successful acknowledgements.
- [x] Lost responses after commit recover without duplicate effects.
- [x] Old input cannot regress current state.
- [x] Missing data and delayed concerns are visible.
- [x] Generated IDs reconcile with server, pending, and quarantine sets.

Run the failure matrix below against real PostgreSQL. Demonstrate actual transport disconnection, buffering, recovery, and verification. Done requires the common gate and passing durability tests.

**Verification on 2026-11-07.** M1 already had durable SQLite generation, stable sequences and receipt replay. Its retry loop treated every error as transient. M2 already protected current pointers and saved historical assessments. Its inbox only exposed risk episodes, its worker only checked escalation, and readiness had no worker heartbeat. M3 extended those paths in place. The migration groups existing M2 historical concerns into review episodes and preserves legacy M1 receipts.

| Check run | Observed result |
|---|---|
| `docker compose -p wardzero-m3-check up -d --build --wait` with `APP_PORT=18013`, `docker compose config -q`, and `alembic current` in the app | Compose, strict TypeScript and the production build passed. The isolated app reported `0006_data_quality (head)`. Regenerated the frontend declarations from its OpenAPI document with openapi-typescript 7.10.1. |
| `docker compose -p wardzero-m3-check exec -T app python -m pytest -q` | 47 passed against real PostgreSQL, with one existing TestClient deprecation warning. Checks include the 30-second boundary, stale and last-known snapshots, an incomplete high during a gap, three consecutive eligible recovery readings, replay and out-of-order handling, migration from M1/M2, overdue worker readiness, transaction rollback and competing acknowledgement/escalation. |
| `docker compose -p wardzero-m3-check exec -T simulator python -m unittest discover -s simulator` | 6 passed. Covered SQLite write failure, stable replay, retryable HTTP statuses, both Retry-After formats, quarantine and exact ID-set discrepancies including overlaps and equal-count substitutions. |
| `python scripts/test-recovery.py` | Project `wardzero-m3-5175c750cd` accumulated **24 pending frames** during an actual network disconnect. All three patients went stale and opened gaps. Reconnecting drained the queue and exposed a historical concern. During a backend stop, the simulator restarted with the same pending IDs and per-device sequences continued. On app startup a persisted overdue review escalated once. |
| PostgreSQL stop and post-commit response loss in the same run | During the DB outage, a valid ingestion request returned 503, liveness returned 200, and SQLite accepted no additional receipts. Uploads drained after restart. The proxy dropped the committed receipt for `af2ce5b6-ecc4-4947-a52a-b119cfc4bc17`. Retry left exactly one reading, assessment and alert event. |
| Frozen ID comparison in the same run | All **55 generated valid IDs** matched all 55 PostgreSQL IDs, with zero pending or quarantined. A second fixture verified **58 generated = 56 stored + 1 pending + 1 quarantined** with empty discrepancy and overlap sets. A real 422 quarantined the invalid device frame while the following valid frame uploaded. Both named volumes were retained. |
| `node scripts/test-quality-ui.cjs wardzero-m3-check` with Playwright and headless Edge | The offline browser displayed refresh failure. On reconnect it showed a saved monitoring gap, stale data and last known concern. A new incomplete high reading showed the delay and the high breach. A repeat run selected the current assignee and matched the rendered historical reading UUID to the stored review assessment before and after reload. |
| `./scripts/test-monitoring.ps1` and `./scripts/test-readiness.ps1` with `COMPOSE_PROJECT_NAME=wardzero-m3-check` and `APP_PORT=18013` | All three rendered IDs matched SQLite and server history across a real app restart. Readiness went 200, 503, 200 across a PostgreSQL stop/start. Liveness stayed 200 during the outage. |

The first matrix run exposed an ephemeral test-port change after the app restart. The runner now rediscovers the published port, and the full matrix passed on rerun. A clock fixture initially placed a gap-opening event in the future relative to acknowledgement. The corrected boundary test uses a past monitoring start. Local Windows temporary-file restrictions required an authorized rerun of the simulator tests, which also passed inside Compose. The QA dashboard is available on loopback port 18013. The failure-matrix projects are stopped with their volumes retained. Local documentation links and anchors and `git diff --check` passed. No open M3 blockers.

### M4 — Historical trends and observations

Depends on M3. Implement median comparisons, sample/gap eligibility, observation capture/expiry, combination rules, and history charts. Likely areas are trends/observations/risk and frontend history/forms.

- [ ] Both deterministic trend scenarios produce expected findings.
- [ ] Insufficient samples and gaps suppress unsupported trend conclusions.
- [ ] Structured observations affect concern according to approved rules.
- [ ] Clearing and expiry remove observation contributions.
- [ ] Explanations reference stored evidence.

Test window boundaries, sample counts, gaps, observation replay, expiry, clearing, and combined conditions using a controllable clock. Demonstrate falling SpO2 plus breathlessness. Done requires the common gate and traceable contextual findings.

### M5 — Escalation and lifecycle completion

Depends on M4. Implement persisted deadlines, backup assignment, resolution conditions, higher-priority reopening, and response timing. Likely areas are lifecycle, periodic loop, inbox, and resolution form.

- [ ] Due alerts escalate within one five-second loop interval.
- [ ] Acknowledgement cancels pending escalation.
- [ ] Restart processes overdue work exactly once at the state-transition level.
- [ ] Concurrent actions preserve consistent assignment and history.
- [ ] Resolution conditions are enforced server-side.
- [ ] Higher priority requires acknowledgement again.

Test deadlines with a fake clock, restart recovery, acknowledgement/escalation races, repeated commands, and priority increases. Demonstrate primary timeout → backup acknowledgement → recovery → resolution. Done requires the common gate and durable lifecycle history.

### M6 — Real-time dashboard polish

Depends on M5. Implement WebSocket invalidation, reconciliation, fallback polling, readable charts, accessible actions, status banners, and loading/error states. Likely areas are realtime, frontend queries, components, and styles.

- [ ] Committed changes normally display within two seconds on the demo laptop.
- [ ] Reconnection restores missed alerts from PostgreSQL.
- [ ] Failed mutations retain drafts and display errors.
- [ ] Stale/unknown data is clearly identified.
- [ ] The page is usable at a standard laptop viewport with keyboard-accessible actions.

Run UI mutation/error tests, stale rendering checks, reconnect tests, typecheck/build, and a Playwright caregiver flow. Demonstrate the complete workflow through the finished dashboard. Done requires the common gate and usable disconnected/reconnected states.

### M7 — Full verification and submission

Depends on M6. Complete scenario scripts, acceptance runner, operational documentation, and recording. Likely areas are tests, scripts, and docs.

- [ ] Fresh startup follows documented commands.
- [ ] The complete demo passes twice.
- [ ] Reading IDs reconcile after recovery.
- [ ] Alert state and history survive restart.
- [ ] Required checks pass and limitations are documented.
- [ ] A reproducible tagged submission and backup recording are prepared within the authorized workflow.

Run backend suite, frontend tests/typecheck/build, selected end-to-end tests, real outage rehearsal, and a short continuous run. Done requires the common gate and reproducible submission evidence.

## Failure acceptance matrix

| Experiment | Required assertion |
|---|---|
| Disconnect simulator from Compose network | Sampling continues, buffer grows, reconnect drains it |
| Stop/restart backend | Buffered frames replay and committed state survives |
| Restart simulator during outage | Buffer and device sequences survive |
| Replay identical frame | One reading and one original assessment effect |
| Drop response after server commit in test harness | Retry produces no duplicate persisted effects |
| Stop/restart PostgreSQL | Requests receive no false success and recover afterward |
| Submit older unseen frame | History includes it, current pointer stays monotonic, concerning evidence remains reviewable |
| Generate nulls or stop one patient's frames | Data quality degrades visibly |
| Disconnect browser during alert creation | Reconnect reloads the saved alert |
| Restart backend across escalation deadline | Saved deadline produces one escalation |
| Compete acknowledgement with escalation | One consistent transition and complete history |

Freeze generation and drain uploads before exact ID reconciliation. For valid fixtures, pending and quarantine sets should be empty and all locally committed IDs should exist on the server.

## Demo sequence

1. Show stable patients and the dashboard.
2. Trigger falling SpO2 and record breathlessness.
3. Inspect the exact evidence and alert explanation.
4. Leave the primary alert unanswered and show backup escalation.
5. Acknowledge as backup.
6. Disconnect the simulator's real network and inspect its growing buffer.
7. Restore connectivity and show replay with preserved alert history.
8. Run identifier verification.
9. Trigger recovery and resolve the episode.

## Repository and documentation roadmap

Create backend/app modules for api, db, ingestion, risk, observations, alerts, and realtime. Add backend/migrations and backend/tests. Create frontend/src areas for api, components, and features, plus frontend/tests. Add simulator/scenarios and simulator/tests, config/demo_rules.json, scripts, tests/e2e, Compose, and environment examples incrementally.

Add README startup/test guidance, API examples, database references, and DEMO_RUNBOOK when corresponding work exists. Maintain important decisions in DECISIONS.md. OpenAPI is the implemented REST contract source.

## Risks and contingency

Resolve Docker readiness first. Keep the frontend to one page and one chart library. Preserve transaction boundaries, database constraints, time ordering, and saved deadlines. Use fake clocks to prevent slow/flaky timer tests. Build images and assets before judging to avoid runtime internet dependencies.

Spend contingency on setup, integration defects, performance, and rehearsal. Simplify decoration, chart options, and additional scenarios if needed. Keep durable ingestion, reliable lifecycle behavior, basic history/context, and failure verification in scope.

## Handoff log

| Date | Work | Evidence and next step |
|---|---|---|
| 2026-11-06 | Persistent documentation baseline | Four requested Markdown documents created. Application milestones pending. Next implementation step is M0 when requested. |
| 2026-11-06 | M0 environment and contracts complete | Docker Desktop started and Git initialized with user approval. All five M0 criteria verified above. App and database left healthy. No open M0 blockers. Await authorization for M1. |

M0 structure follow-up: separated health routes from FastAPI startup and the environment screen from React startup. `docker compose up --build --wait --wait-timeout 120` passed, including strict TypeScript and the production bundle. `docker compose exec -T app python -m pytest -q` passed all three tests. `./scripts/test-readiness.ps1` verified readiness 200 → 503 → 200 across a PostgreSQL stop and restart. M0 remains complete.

M0 layout revision: extracted API routes, readiness services, response models and database configuration into backend packages. Separated frontend API access, pages and styles. Repeated the Compose build, pytest and outage script above against the revised layout. Both services started healthy, all three tests passed, and readiness recovered after restarting PostgreSQL. See the [project layout](../README.md#project-layout).

**2026-11-06 — M1 handoff.** Durable monitoring for all three synthetic patients passed the checks above. Startup and rerun instructions are in the [README](../README.md#verify-m1). No open M1 blockers. Changes are uncommitted as requested. Await authorization before starting M2.

**2026-11-06 — M2 handoff.** All five acceptance items passed. The [walkthrough](../README.md#verify-m2) reproduces the explanation and acknowledgement in a separate Compose project. No open M2 blockers. Changes are uncommitted at the user's request. M3 awaits separate authorization.

Future entries should include milestone status, actual commands/results, outstanding issues, and the next authorized action. Preserve historical observations rather than silently rewriting them as current facts.

**M2 live demonstration follow-up.** The [live walkthrough](../README.md#verify-m2) now uses the main dashboard and an on-demand simulator command. Rebuilt the simulator with `docker compose up --build -d --wait simulator`. Both tests passed with `docker compose exec -T simulator python -m unittest simulator.test_buffer`. In a disposable three-service Compose project, Edge showed the baseline, then Watch and High on Mira's card and alert after `docker compose exec -T simulator python -m simulator.trigger_alert`. All three patients advanced to new reading IDs, Mira returned to baseline, and one episode remained. The presentation stack on port 8010 was checked separately with all three readings present and zero active alerts. M3 remains pending.

**Live caregiver handoff follow-up.** The requested demo rotation, persisted deadlines, backup assignment and renewed acknowledgement are implemented on the main stack. Docker Compose rebuilt successfully. The app pytest suite passed 42 tests, including a real PostgreSQL deadline made due and processed by the running worker, primary rejection after reassignment, backup acknowledgement, and reopening following recovery. All three simulator tests passed, including Mira → Aryan → Lena → Mira across command invocations. Full M5 verification, resolution and broader recovery testing remain pending. Work is uncommitted.

**Caregiver inbox follow-up.** Filtered the polling dashboard by the selected caregiver's current assignments. The Compose build passed strict TypeScript and Vite. In Edge, a simulated reassignment in the dashboard response moved the alert into Sam's selected inbox on polling and out of Alex's inbox. The prior PostgreSQL worker test covers the actual deadline transition.

**2026-11-07 — M3 handoff.** All seven failure-recovery and data-quality criteria passed. See the M3 verification table for commands, reconciliation counts and recovery evidence. Changes are uncommitted at the user's request. The next planned milestone is M4, pending separate authorization.

**2026-11-07 — M3 commit authorization.** The user subsequently authorized committing the completed M3 implementation, tests and documentation. Verification evidence remains recorded above. M4 awaits separate authorization.
