# Implementation plan and progress

Updated 2026-11-07. Read [AGENTS.md](../AGENTS.md) before work. The approved behavior is in [ARCHITECTURE.md](ARCHITECTURE.md), with rationale in [DECISIONS.md](DECISIONS.md).

## Current state

M0 through M5 are complete. The simulator retains frames across transport and service outages. PostgreSQL stores threshold/trend/observation evidence, monitoring gaps, delayed-review episodes and the complete caregiver lifecycle. The polling dashboard provides context, backup escalation, acknowledgement, recovery progress, resolution and saved response history. The [M5 walkthrough](../README.md#verify-m5) describes the implemented workflow and verification. The user authorized M5 only, then authorized a local commit after the uncommitted handoff. No push is authorized.

The workspace was empty when documentation creation began. During planning on 2026-11-05, Python and Node were absent from the inspected shell PATH. Docker CLI was present, its daemon was unreachable, and its user configuration could not be read in that session. Recheck these observations during M0. They do not establish the machine's permanent configuration.

The M0 through M5 sections record executed checks. Earlier commit authorizations remain historical entries in the handoff log. M5 is complete; the user subsequently authorized a local commit without pushing. M6 and M7 remain pending and were not started.

## Budget and priorities

The budget is 48 development hours, with 40 planned hours and eight contingency hours. P0 includes monitoring, durable ingestion, threshold rules, data quality, trends, observations, alerts, acknowledgement, escalation, resolution, dashboard, and actual failure recovery. Competitive differentiation comes from depth in these capabilities.

P1, after P0 passes, includes a compact reliability export, connection-gap visualization, and one extra scenario. P2 future work includes ML forecasting, LLM interpretation, attendance, real authentication, external messaging, hardware, hosting, and scaling.

| Milestone | Hours | Cumulative | Status |
|---|---:|---:|---|
| M0 Environment and contracts | 3 | 3 | Complete |
| M1 Durable monitoring vertical slice | 6 | 9 | Complete |
| M2 Explained alerts and acknowledgement | 6 | 15 | Complete |
| M3 Failure recovery and data quality | 7 | 22 | Complete |
| M4 Historical trends and observations | 5 | 27 | Complete — local commit authorized; no push |
| M5 Escalation and lifecycle completion | 4 | 31 | Complete — verified; local commit authorized; no push |
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

- [x] Both deterministic trend scenarios produce expected findings.
- [x] Insufficient samples and gaps suppress unsupported trend conclusions.
- [x] Structured observations affect concern according to approved rules.
- [x] Clearing and expiry remove observation contributions.
- [x] Explanations reference stored evidence.

Test window boundaries, sample counts, gaps, observation replay, expiry, clearing, and combined conditions using a controllable clock. Demonstrate falling SpO2 plus breathlessness. Done requires the common gate and traceable contextual findings.

**Implementation plan, 2026-11-07 (before code changes).** Inspection found SQLAlchemy Core transactions rather than ORM entities, one unique assessment per reading, threshold-only finding contracts, a patient-first lock shared by ingestion and lifecycle operations, and a five-second startup/periodic freshness and escalation loop. History is already paginated by observed time. Recharts is pinned but unused. Observations, trend summaries, and history charts are absent. Existing escalation is retained; M5 resolution and M6 WebSockets are outside this work.

1. Add migration `0007_context`: constrained observation storage, actor attribution and server timestamps, observation-triggered/expiry assessments, JSONB trend summaries, and a persisted next-expiry deadline. Preserve existing reading receipts with a unique index restricted to reading-triggered assessments.
2. Implement pure median comparisons anchored to the eligible current reading: `(t-120s,t-60s]` and `(t-60s,t]`. Require eight valid metric samples in each window and gaps at most ten seconds, including the outer edges. Store window bounds, medians, signed change, eligibility reason, and every contributing reading ID/time/value. Historical ingestion stays threshold-only; future current evaluations can use recovered history.
3. Add assigned-primary/backup observation POST with strict tag/boolean/note validation, server creation/expiry, identical replay and conflicting UUID rejection. Latest-per-tag selection precedes expiry filtering so earlier positives never resurrect. Evaluate threshold, trends and active observations atomically under the patient lock; stale readings cannot support current combination rules.
4. Apply Watch floors and the breathlessness/SpO2 High combination. Clearing/expiry remove only observation contributions. Keep original evidence and peak alert priority; do not implement risk resolution. Process due expiry in the existing loop before readiness, with persisted scheduling to avoid repeated effects.
5. Extend generated OpenAPI types, share the existing demo caregiver selector, add patient/metric history charts with missing-data gaps, trend explanations, active observation attribution/expiry, and a form retaining uncertain submissions and UUIDs for retry. Keep polling and display notes without interpretation.
6. Verify deterministic rule boundaries, sample/gap suppression, evidence references, all tags/combinations, clear/expiry, authorization/validation, replay/conflict/concurrency, rollback, upgrade compatibility and startup expiry using real PostgreSQL and injected evaluation times. Run the full backend and simulator regressions, strict TypeScript/production build, and an isolated browser scenario showing falling SpO2 plus breathlessness, clearing, chart data, and failed-form retry.
7. Record exact commands and outcomes here and document runnable M4 usage in README. Mark M4 complete only after all five criteria pass. Leave all changes uncommitted as requested.

**Verification on 2026-11-07.** The plan above was recorded before code changes. M4 extends the existing transaction, patient lock, history API, polling dashboard and periodic worker. No new dependency or service was added. The primary local stack was upgraded with existing volumes preserved.

| Check run | Observed result |
|---|---|
| `docker compose -p wardzero-m4-check up -d --build --wait app` with `APP_PORT=18014` | Isolated PostgreSQL/app startup passed. Strict TypeScript and Vite production build passed. Recharts is the already-pinned chart dependency. Vite reports its nonblocking dependency-directive and bundle-size warnings (approximately 647 kB uncompressed). |
| `docker compose -p wardzero-m4-check exec -T app python -m pytest -q` | **69 passed**, including all 47 prior checks, with one existing TestClient deprecation warning. New checks cover both exact trend thresholds, median outlier resistance, subthreshold changes, midpoint/outer bounds, exactly eight samples/ten-second gaps, missing samples/nulls/edge gaps, all observation tags, combination on an incomplete current reading, stale/historical exclusion, clearing, exact expiry, no resurrection, stored evidence, and stable reading receipts after reassessment. |
| PostgreSQL persistence checks in that same suite | Four concurrent observation copies produced one 201 and three 200 responses with one observation/assessment/event. Conflicting payloads/actors/patients returned 409; assignment and strict validation were enforced. A final audit constraint failure rolled back observation, assessment, patient state, and alert. Concurrent reading/observation writes retained one consistent risk episode. Startup-check expiry ran once. Ingestion processing an expired observation removed it from latest alert evidence. Populated M3 upgrade and existing M1/M2 migration regressions passed. |
| `docker compose -p wardzero-m4-check run --rm --no-deps --build simulator python -m unittest discover -s simulator` | **6 passed**, preserving durable buffering, retry/quarantine behavior, scenario rotation, and identifier verification. |
| OpenAPI generation with `openapi-typescript@7.10.1` from the isolated server | Checked-in strict frontend declarations regenerated successfully. No dependency manifest/lock changes. |
| `node scripts/test-context-ui.cjs` with bundled Playwright and headless Edge | Passed twice; final project `wardzero-m4-ui-1794038665486`. The browser displayed both supported median changes and the 24-reading chart; saved breathlessness changed Watch to High; clearing returned Watch. Verified backup attribution and literal note rendering. Dropping an actual committed observation response, reloading, and retrying retained exactly one database row. A real app stop/restart processed overdue expiry once. No browser page errors. Screenshot `m4-browser-evidence.png` inspected; test projects stopped with evidence volumes retained. |
| `python scripts/test-recovery.py` | Full real failure matrix passed on M4 in `wardzero-m3-7d18142819`. Network disconnection accumulated **24 pending frames** and three monitoring gaps. Simulator restart retained pending IDs/sequences during app outage; restart escalated an overdue review once. PostgreSQL outage returned no false success. Lost receipt `3172ef75-c03b-4e64-bc93-096052f23558` left exactly one reading/assessment/event. **55 generated = 55 stored**, then **58 generated = 56 stored + 1 pending + 1 quarantined**, with empty discrepancy/overlap sets. Services stopped and volumes retained. |
| `node scripts/test-quality-ui.cjs wardzero-m4-check` | M3 browser regression passed: refresh failure, stale/last-known values, saved monitoring gap on reconnect, incomplete High, delayed delivery, and historical evidence across reload. Updated its caregiver selector to use the accessible label now that M4 adds other selects. Simulator restored afterward. |
| `docker compose up -d --build --wait app`, `docker compose exec -T app alembic current`, and `docker compose config -q` | Regular local app healthy at port 8010, applied `0007_context (head)`, valid configuration. Existing PostgreSQL and simulator volumes preserved. |
| Final local HTTP and documentation checks | Regular dashboard returned readiness `ready`, three fresh patients, and the M4 observation contract. All 19 local Markdown links/anchors across the five project documents passed. `git diff --check` passed. |

Review corrected an ingestion/expiry race that could leave expired observation evidence as the latest alert evidence; its regression passes. The first backend run's old rule-version expectation was updated for `demo-context-v1`. Temporary QA services are stopped with their evidence volumes retained; the regular dashboard remains running. No open M4 blockers. The commit step is explicitly waived by the user's no-commit instruction. M5 resolution and M6 realtime remain outside this handoff.

### M5 — Escalation and lifecycle completion

Depends on M4. Implement persisted deadlines, backup assignment, resolution conditions, higher-priority reopening, and response timing. Likely areas are lifecycle, periodic loop, inbox, and resolution form.

**Implementation plan executed, 2026-11-07.** The user authorized M5 only and prohibited commits. Inspection confirmed primary/backup foreign keys and seeds, saved deadlines, patient-first locking, a five-second startup/periodic worker, and caregiver inbox filtering already existed. Completed resolution with durable recovery evidence and idempotent commands; exposed deadlines, response timing and lifecycle history; added the resolution form. Verified controlled-clock boundaries, PostgreSQL races/rollback/replays, real restart recovery and the browser primary → backup → acknowledgement → recovery → resolution flow. Preserved M4 context rules and kept M6 pending.

- [x] Due alerts escalate within one five-second loop interval.
- [x] Acknowledgement cancels pending escalation.
- [x] Restart processes overdue work exactly once at the state-transition level.
- [x] Concurrent actions preserve consistent assignment and history.
- [x] Resolution conditions are enforced server-side.
- [x] Higher priority requires acknowledgement again.

Test deadlines with a fake clock, restart recovery, acknowledgement/escalation races, repeated commands, and priority increases. Demonstrate primary timeout → backup acknowledgement → recovery → resolution. Done requires the common gate and durable lifecycle history.

**Verification on 2026-11-07.** All six criteria passed. Migration `0008_resolution` preserves existing deadlines, assignments, evidence and commands while adding recovery and response metadata. Resolution enforces assignment, acknowledgement, note and kind-specific recovery under the existing patient lock. Original/peak evidence and earlier response cycles remain durable. The [README](../README.md#verify-m5) documents the API and demonstration.

| Check run | Observed result |
|---|---|
| `docker compose up -d --build --wait app` | App/database healthy; strict TypeScript and Vite production build passed. Existing volumes preserved. |
| `docker compose exec -T app python -m pytest -q` | **83 passed** on real PostgreSQL, including all existing regressions. M5 covers exact 30/60-second boundaries with controlled time, no early or repeated escalation, cancellation, response timing, shortened deadlines, higher-priority reopening across incomplete data, old acknowledgement replay after reassignment, concurrent resolution replay, acknowledgement/escalation and resolution/new-High races, note/assignment/recovery validation, stale and incomplete recovery, historical/replayed input, active context and supported trends, transaction rollback and M4 upgrade compatibility. |
| `docker compose up -d --build --wait simulator` and `docker compose exec -T simulator python -m unittest discover -s simulator` | **6 passed** after refreshing the previously stale running simulator image. Its earlier run exposed only three older tests; the final run used all current tests. Synthetic transport errors/quarantine logs are expected test fixtures. Persistent simulator buffer preserved. |
| `node scripts/test-lifecycle-ui.cjs` with bundled Node/Playwright and Edge | Passed twice in isolated projects. Final project `wardzero-m5-ui-1794041094755`: actual primary timeout escalated **523 ms** after the saved deadline (first run 681 ms), within one five-second loop. Browser completed backup acknowledgement → rejected premature resolution/draft retention → three recovered readings → resolution. A real committed resolution response was dropped and retried after reload with one saved event; literal note and response timings rendered correctly. |
| Same M5 script, real app stop/start and second restart | A different saved deadline was made overdue while the app was stopped. Startup processed one escalation before readiness; a second restart retained exactly one escalation. Previously resolved alert, actor, note, timings and entire event history survived unchanged. QA services stopped and evidence volumes retained. |
| `node scripts/test-context-ui.cjs` | M4 browser regression passed on the M5 build: both trends, stored chart, combined High, clearing, actor attribution, literal notes, dropped committed observation response/reload retry and real restart expiry. Project `wardzero-m4-ui-1794041050134` stopped with evidence retained. |
| `docker compose exec -T app python -m pytest -q tests/test_lifecycle.py` after expanding the legacy migration fixture | **14 passed**. Also confirms a previous response cycle's escalation timestamp does not carry into a reopened cycle. Two derived timestamps from the interim development migration on the regular stack were refreshed from their saved events; source history and assignments were preserved. |
| `docker compose exec -T app alembic current`, `docker compose config -q`, loopback HTTP, local link check and `git diff --check` | Migration `0008_resolution (head)`, valid Compose configuration, readiness `ready` and three fresh patient snapshots at port 8010. All **21** local Markdown links/anchors passed. Frontend sources decode as UTF-8 and the final diff check passed. |

Review added coverage for an incomplete frame concealing a renewed priority rise and for legacy command replay after migration. One intermediate run failed because the new migration fixture omitted its opening event; the fixture was corrected and the complete suite then passed. Screenshot review corrected the new form's text encoding and added its input styling; the final browser run verified the corrected build. Existing non-failing Starlette deprecation and Vite module/chunk warnings remain. No open M5 failures or blockers. Full M7 outage rehearsal was not rerun for this milestone. The common gate's commit step is waived by the user's explicit no-commit instruction.

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

**2026-11-07 — M4 handoff.** Inspected the approved documents and actual code, recorded the detailed implementation plan, then completed all five M4 criteria. Evidence is in the M4 table above. The regular dashboard runs migration `0007_context` with persistent data preserved. All work remains uncommitted as requested. No open M4 failures or blockers. The next planned milestone is M5 lifecycle completion, which requires separate authorization; no next-milestone work was started.

**2026-11-07 — M4 commit authorization.** The user subsequently authorized committing the completed M4 implementation, tests, and documentation locally, with no push. The verification evidence above remains applicable; the pre-commit diff check passed. No additional milestone work was authorized.

**2026-11-07 — M5 handoff.** Completed all six M5 criteria and the caregiver primary timeout → backup acknowledgement → recovery → resolution demonstration. Final evidence: 83 backend tests, six simulator tests, strict TypeScript/build, M5 browser/restart/lost-response checks and M4 browser regression passed. Saved lifecycle history and response timing survive restart. The regular dashboard runs at port 8010 with persistent volumes preserved. No open failures or blockers; all M5 changes remain uncommitted. The next planned step is M6, requiring separate authorization; no M6 or M7 implementation was started.

**2026-11-07 - M5 commit authorization.** The user authorized committing the completed M5 implementation, tests and documentation locally, with no push. The verification evidence above remains applicable; the pre-commit diff check passed. No further milestone work was authorized.
