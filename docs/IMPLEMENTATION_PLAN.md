# Implementation plan and progress

Updated 2026-11-08. Read [AGENTS.md](../AGENTS.md) before work. The approved behavior is in [ARCHITECTURE.md](ARCHITECTURE.md), with rationale in [DECISIONS.md](DECISIONS.md).

## Current state

M0 through M6 are complete. The simulator retains frames across transport and service outages. PostgreSQL stores threshold, trend, and observation evidence, monitoring gaps, delayed-review episodes, and the complete caregiver lifecycle. The dashboard uses post-commit WebSocket hints, REST reconciliation, polling, and explicit synchronization and cached-data states. The [demo runbook](DEMO_RUNBOOK.md#full-acceptance-command) documents the verification workflow. M6 was committed as `db7cd2d` after the subsequent authorization recorded below.

The Bubble-inspired dashboard redesign is implemented and running on the regular Compose stack. The sidebar links to sections of one page, and the chart and observation form share the selected patient. See the redesign handoff below for browser and service evidence.

The workspace was empty when documentation creation began. During planning on 2026-11-05, Python and Node were absent from the inspected shell PATH. Docker CLI was present, its daemon was unreachable, and its user configuration could not be read in that session. Recheck these observations during M0. They do not establish the machine's permanent configuration.

The M0 through M6 sections record executed checks. Earlier commit authorizations remain historical entries in the handoff log. M7 implementation and full verification passed, including two recorded complete demos. M7 is not fully complete: the user prohibits commits and explicitly chose to leave the Git-tag criterion pending. The untagged source archive does not substitute for a Git tag. See the [M7 runbook](DEMO_RUNBOOK.md) and evidence below.

## Budget and priorities

**Subsequent M6 authorization, 2026-11-07.** After the uncommitted handoff recorded above, the user authorized committing the completed M6 changes and pushing the current branch to the configured repository. This supersedes the earlier no-commit restriction for M6. Existing verification evidence remains applicable; the pre-commit diff check passed. No M7 implementation was authorized.

The budget is 48 development hours, with 40 planned hours and eight contingency hours. P0 includes monitoring, durable ingestion, threshold rules, data quality, trends, observations, alerts, acknowledgement, escalation, resolution, dashboard, and actual failure recovery. Competitive differentiation comes from depth in these capabilities.

P1, after P0 passes, includes a compact reliability export, connection-gap visualization, and one extra scenario. P2 future work includes ML forecasting, LLM interpretation, attendance, real authentication, external messaging, hardware, hosting, and scaling.

| Milestone | Hours | Cumulative | Status |
|---|---:|---:|---|
| M0 Environment and contracts | 3 | 3 | Complete |
| M1 Durable monitoring vertical slice | 6 | 9 | Complete |
| M2 Explained alerts and acknowledgement | 6 | 15 | Complete |
| M3 Failure recovery and data quality | 7 | 22 | Complete |
| M4 Historical trends and observations | 5 | 27 | Complete — local commit authorized; no push |
| M5 Escalation and lifecycle completion | 4 | 31 | Complete — M6 regression passed; prior local commit preserved |
| M6 Real-time dashboard polish | 5 | 36 | Complete — verified; commit and push authorized |
| M7 Full verification and submission | 4 | 40 | Verification passed — Git-tag criterion pending by user instruction |
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

The [demo runbook](DEMO_RUNBOOK.md#prerequisites-and-startup) gives current startup instructions. The running app exposes OpenAPI and readiness endpoints. The existing [planned API contracts](ARCHITECTURE.md#public-interfaces) cover later milestones.

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

**Verification on 2026-11-07.** All six criteria passed. Migration `0008_resolution` preserves existing deadlines, assignments, evidence and commands while adding recovery and response metadata. Resolution enforces assignment, acknowledgement, note and kind-specific recovery under the existing patient lock. Original/peak evidence and earlier response cycles remain durable. The [technical documentation](TECHNICAL_DOCUMENTATION.md#8-alert-generation-acknowledgement-and-escalation) describes the implemented lifecycle.

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

**Approved implementation plan, executed 2026-11-07.** The user approved the read-only inspection plan before edits and authorized M6 only, without commits. Preserve the implemented M0–M5 features. Add `/api/v1/ws` with post-commit hints, ten-second heartbeats, bounded queues and slow-client cleanup; retain one worker and the existing periodic loop. Reconcile existing REST queries on connection/reconnection, retain 15-second connected and five-second disconnected polling, and expose synchronization/cached-data states. Polish the existing charts, forms and keyboard/laptop layout. Verify post-commit/rollback behavior, queue isolation, real browser reconnect, polling fallback, two-second display latency, mutation retries, stale rendering and the caregiver flow. Run backend/simulator and M4/M5 browser regressions, typecheck/build and documentation checks. Use isolated loopback Compose fixtures and preserve volumes. M5 remains complete; record its regression evidence alongside M6 results. M7 is not authorized.

- [x] Committed changes normally display within two seconds on the demo laptop.
- [x] Reconnection restores missed alerts from PostgreSQL.
- [x] Failed mutations retain drafts and display errors.
- [x] Stale/unknown data is clearly identified.
- [x] The page is usable at a standard laptop viewport with keyboard-accessible actions.

Run UI mutation/error tests, stale rendering checks, reconnect tests, typecheck/build, and a Playwright caregiver flow. Demonstrate the complete workflow through the finished dashboard. Done requires the common gate and usable disconnected/reconnected states.

**Verification on 2026-11-07.** All five M6 criteria passed. Existing transactions, thresholds/context, recovery rules, persistence and caregiver attribution remain authoritative. No migration, frontend dependency, service or additional periodic worker was added. The only runtime dependency addition is hash-pinned `wsproto==1.3.2`. The [technical documentation](TECHNICAL_DOCUMENTATION.md#9-data-reliability-and-recovery) describes live updates, fallback and retries. The [demo runbook](DEMO_RUNBOOK.md#full-acceptance-command) gives reproducible checks.

| Check run | Observed result |
|---|---|
| `docker compose -p wardzero-m6-check up -d --build --wait app` with `APP_PORT=18016` | Isolated app/database healthy. Strict TypeScript and Vite production build passed. Dependency hashes and `pip check` passed. The final M6 browser fixture also rebuilt the final frontend successfully. |
| `docker compose -p wardzero-m6-check exec -T app python -m pytest -q` | **92 passed** on real PostgreSQL: all 83 prior tests plus nine realtime cases. Separate-connection inspection confirms a reading is committed at hint publication; rejected audit writes emit no reading hint; publication failure preserves successful receipts. Covers observation/acknowledgement/resolution hints, silent identical retries, rejected resolution, periodic gap/expiry/escalation transitions, repeated checks, multi-client delivery, heartbeat, queue overflow, blocked sends and connection cleanup. |
| `docker compose -p wardzero-m6-check run --rm --no-deps --build simulator python -m unittest discover -s simulator` | **6 passed**. Durable SQLite/retry/quarantine/identifier behavior remains intact. Expected synthetic outage/quarantine messages appeared. |
| `node scripts/test-realtime-ui.cjs` with bundled Node/Playwright and headless Edge | Final project `wardzero-m6-ui-1794072605298` passed. Reading-to-render upper bounds, including request overhead: **985, 913 and 948 ms**. New alert: **795 ms**. Externally saved observation clear: **98 ms**. All under two seconds. |
| Transport and UI checks in the same M6 script | A real TCP proxy severed browser transport while the backend committed a new alert. The UI displayed refresh failure and cached/unknown state; reconnection restored the saved alert, latest reading and selected history through REST. WebSocket-only failure retained working polling. Pausing socket forwarding tested silent heartbeat loss and automatic recovery. Real app restart restored the connection and preserved resolved history. |
| Mutation, rendering and keyboard checks in the same M6 script | Dropped an actual committed acknowledgement response; reload/retry reused its command with one PostgreSQL event. Failed observation/resolution submissions retained exact payloads and notes through reload. Keyboard navigation activated the skip link, metric selector, acknowledgement and lifecycle disclosure. Verified unavailable/incomplete/real stale states, last-known concern, readable chart dimensions, no horizontal page overflow at **1366×768**, and zero browser page errors. Inspected screenshots `m6-browser-evidence.png` and the corrected chart render. |
| `node scripts/test-context-ui.cjs` after the chart correction | **M4 browser regression passed**, project `wardzero-m4-ui-1794045400209`: both trends, visible stored-reading chart, combination High, clearing, attribution, literal notes, lost-response replay and real restart expiry. Added an actual SVG-dimension assertion so hidden zero-width plots cannot pass solely because chart markup exists. |
| `node scripts/test-lifecycle-ui.cjs` against the final reconnect implementation | **M5 browser/restart regression passed**, project `wardzero-m5-ui-1794072705163`. Primary timeout processed **593 ms** after its saved deadline. Completed backup acknowledgement, premature-resolution rejection, recovery, resolution, lost-response retry and saved response timing/history. Restart processed an overdue escalation once; a second restart preserved one escalation and unchanged resolved history. **M5 remains complete.** |
| `docker compose up -d --build --wait app`, `docker compose exec -T app alembic current`, `docker compose config -q`, and a read-only Edge smoke check | Main app healthy at **127.0.0.1:8010**, OpenAPI version `0.6.0`, migration **0008_resolution (head)** and valid Compose configuration. Browser showed live connection, all three reading IDs advanced, chart width **1126 px**, no horizontal overflow and no page errors. Existing main volumes preserved. |
| Local Markdown/UTF-8 validation, `git diff --check`, and `docker compose -p wardzero-m6-check down` | All **22** local Markdown links/anchors across the five project documents passed; frontend/document text decoded correctly. Diff check passed. Isolated M6 inspection services stopped; all fixture evidence volumes retained. The main stack and pre-existing auxiliary stacks were left intact. |

Review found and corrected three issues: the first M6 browser fixture assumed command IDs were exposed in the alert-history API (it now verifies PostgreSQL directly); a new CSS width limit hid Recharts' plot despite existing SVG markup (removed and covered by dimension checks); and a silent peer delayed the browser close handshake (the watchdog now enters fallback immediately). The final M6 suite passed after these corrections. Existing non-failing Starlette deprecation and Vite directive/chunk-size warnings remain. The common completion gate's commit step is waived by the user's explicit no-commit instruction. M7's full outage rehearsal, submission/tag and recording work were not started.

### M7 — Full verification and submission

Depends on M6. Complete scenario scripts, acceptance runner, operational documentation, and recording. Likely areas are tests, scripts, and docs.

**Authorization and scope, 2026-11-08.** The user authorized M7 only, prohibited commits, and requested consultation on difficulties. Preserve all existing uncommitted changes. Add persistent simulator scenario selections, a fail-fast acceptance runner, the nine-step browser rehearsal with a backup recording, operational documentation, and an explicitly untagged source snapshot with SHA-256 hashes. Reuse existing backend/frontend/browser/failure checks; do not add product features beyond the documented scenarios. The user explicitly elected to leave the Git-tag criterion pending. The common gate's commit step is waived for this working session, but the tagged-submission acceptance item is not waived.

The first rehearsal completed all nine demo stages, reconciled 174 generated/stored IDs and verified exact resolved state through a real app restart. Its final browser assertion timed out because reload reset the caregiver selector to Primary while the resolved archive was assigned to Backup. The test now explicitly reselects Backup after reload. Work paused for consultation; the user authorized the correction, full acceptance suite and two fresh rehearsals. This initial run is retained as diagnostic evidence, not counted as a passing complete demo. The corrected full verification passed below.

- [x] Fresh startup follows documented commands.
- [x] The complete demo passes twice.
- [x] Reading IDs reconcile after recovery.
- [x] Alert state and history survive restart.
- [x] Required checks pass and limitations are documented.
- [ ] A reproducible tagged submission and backup recording are prepared within the authorized workflow.

Run backend suite, frontend tests/typecheck/build, selected end-to-end tests, real outage rehearsal, and a short continuous run. Done requires the common gate and reproducible submission evidence.

**Verification on 2026-11-08.** `python scripts/test-acceptance.py --output artifacts/m7/full-verification` exited **0**, with all **19** recorded checks passing. Its isolated main project was `wardzero-prem7-1b0ace94f9`. `artifacts/m7/full-verification/acceptance.json` records exact commands, exit codes, durations and the source snapshot; adjacent logs retain full output. Host verification used Python 3.14, Node 24, Playwright 1.62.1, Edge and FFmpeg; the application uses the pinned Docker runtimes and lockfiles. The regular demo stack was not changed.

| Check run | Observed result |
|---|---|
| `docker compose -p wardzero-prem7-1b0ace94f9 config -q` and `up --build -d --wait --wait-timeout 120` | Fresh named volumes, migration/seed startup and all three services succeeded on a random loopback port. All three patients delivered fresh readings. Migration is `0009_caregiver_labels (head)`. |
| `docker compose -p wardzero-prem7-1b0ace94f9 exec -T app python -m pytest -q` | **93 passed** on real PostgreSQL, including transactions, constraints, concurrency, migration compatibility, thresholds/trends/context, deadlines, retries and restart behavior. One existing Starlette deprecation warning. |
| `docker compose -p wardzero-prem7-1b0ace94f9 exec -T simulator python -m unittest discover -s simulator` | **7 passed**, including the new persistent scenario selection and committed-frame/sequence checks plus existing buffer, retry, quarantine and exact identifier regressions. Expected synthetic failure messages appeared. |
| `docker build --target frontend -t wardzero-prem7-1b0ace94f9-frontend .` and `docker run --rm wardzero-prem7-1b0ace94f9-frontend npm run typecheck` | Production build and strict TypeScript passed. Browser integration tests below provide frontend tests; no separate Vitest/unit-test command existed or was added. |
| `node scripts/test-dashboard-ui.cjs http://127.0.0.1:32849 artifacts/m7/full-verification` and `node scripts/test-quality-ui.cjs wardzero-prem7-1b0ace94f9` | Passed at 1440, 1024, 768 and 375 px: chart dimensions, no page overflow, navigation, synchronized patient selection, counts and stored readings. Quality tests passed actual staleness, reconnect, last-known concern, incomplete High, delayed delivery and persisted historical evidence. |
| `python scripts/test-recovery.py` | Project `wardzero-m3-3fb0983c35` passed real network/app/database failures and simulator restart. Network loss accumulated **24 pending frames**, three stale patients and three gaps. Saved IDs/sequences survived restart. Database outage produced no false successful receipt. Lost committed receipt `318ed53e-1aec-4998-ac6e-8860f61ee931` retried with exactly one reading, assessment and alert event. **55 generated = 55 stored**; mixed fixture **58 = 56 stored + 1 pending + 1 quarantined**, with empty discrepancy/overlap sets. |
| `node scripts/test-context-ui.cjs` | Passed both trends, combination/observation-only explanations, stored evidence/chart, caregiver attribution, literal notes, lost-response retry and restart expiry. Project `wardzero-m4-ui-1794124519066`. |
| `node scripts/test-lifecycle-ui.cjs` | Passed backup handoff, acknowledgement, recovery, resolution, retained drafts/replay, inbox visibility/order and durable history through two restarts. Real escalation processed **543 ms** after its saved deadline. Project `wardzero-m5-ui-1794124545724`. |
| `node scripts/test-realtime-ui.cjs` | Passed real transport cut, REST reconciliation, polling fallback, silent heartbeat loss, cached/unknown/incomplete/stale states, retained mutation payloads, keyboard/laptop checks and real app restart. Reading render upper bounds **1187, 932, 890 ms**; alert **903 ms**; context clear **119 ms**. No browser page errors. Project `wardzero-m6-ui-1794124613709`. |
| `node scripts/test-demo-ui.cjs artifacts/m7/full-verification/demo-1` | **Complete nine-step demo passed**, project `wardzero-m7-demo-1794124707198`. Continuous run **61.115 seconds / 12 checks**; real backup escalation **997 ms** after deadline; actual network disconnection retained **18 pending frames**. Post-recovery **171/171** IDs and final **186/186** IDs, with no pending/quarantined/missing/unexpected/overlapping IDs. Exact resolved state/history survived real app restart. |
| `node scripts/test-demo-ui.cjs artifacts/m7/full-verification/demo-2` | **Second complete demo passed**, fresh project `wardzero-m7-demo-1794124924394`. Continuous run **61.061 seconds / 12 checks**; escalation **1195 ms** after deadline; **18 pending frames** during network loss. Post-recovery **171/171**, final **186/186**, all discrepancy sets empty. Exact resolved state/history survived restart; no browser page errors in either demo. |
| Backup recording and source packaging | Both demo directories contain `backup-demo.mp4` and `demo.json`. FFprobe verified H.264 at **1366×900**, **194.0** and **197.5** seconds; extracted video frames were visually inspected. Source ZIP preparation verifies all file hashes and excludes `.env`, Git internals and generated artifacts. The acceptance-start source snapshot is `m7-untagged-beb307a40b74`; subsequent changes are documentation only. |
| `python scripts/check-docs.py`, Python AST parsing, `node --check scripts/test-demo-ui.cjs`, `git diff --check` | Passed local links/anchors, syntax and whitespace. Final documentation and package verification are recorded in the handoff below. |

**Remaining criterion.** Backup recordings and a hashed untagged source archive are prepared. A Git tag covering the tested working tree cannot be produced without committing its uncommitted source. The user explicitly chose to leave that part pending; the last checkbox and M7's overall completion therefore remain open. No other M7 implementation/test blocker remains. No commit, tag, push or next-milestone work was performed. The runbook documents startup, full acceptance, scenario controls, outage/reconciliation steps, evidence inspection, explicit reset and prototype/recording limitations.

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

**2026-11-06 — M1 handoff.** Durable monitoring for all three synthetic patients passed the checks above. Startup and rerun instructions are in the [demo runbook](DEMO_RUNBOOK.md#prerequisites-and-startup). No open M1 blockers. Changes are uncommitted as requested. Await authorization before starting M2.

**2026-11-06 — M2 handoff.** All five acceptance items passed. The short simulator trigger reproduces a threshold breach. The [demo runbook](DEMO_RUNBOOK.md#nine-step-recorded-demo) exercises explanation and acknowledgement in an isolated project. No open M2 blockers. Changes are uncommitted at the user's request. M3 awaits separate authorization.

Future entries should include milestone status, actual commands/results, outstanding issues, and the next authorized action. Preserve historical observations rather than silently rewriting them as current facts.

**M2 live demonstration follow-up.** The live walkthrough now uses the main dashboard and an on-demand simulator command. Rebuilt the simulator with `docker compose up --build -d --wait simulator`. Both tests passed with `docker compose exec -T simulator python -m unittest simulator.test_buffer`. In a disposable three-service Compose project, Edge showed the baseline, then Watch and High on Mira's card and alert after `docker compose exec -T simulator python -m simulator.trigger_alert`. All three patients advanced to new reading IDs, Mira returned to baseline, and one episode remained. The presentation stack on port 8010 was checked separately with all three readings present and zero active alerts. M3 remains pending.

**Live caregiver handoff follow-up.** The requested demo rotation, persisted deadlines, backup assignment and renewed acknowledgement are implemented on the main stack. Docker Compose rebuilt successfully. The app pytest suite passed 42 tests, including a real PostgreSQL deadline made due and processed by the running worker, primary rejection after reassignment, backup acknowledgement, and reopening following recovery. All three simulator tests passed, including Mira → Aryan → Lena → Mira across command invocations. Full M5 verification, resolution and broader recovery testing remain pending. Work is uncommitted.

**Caregiver inbox follow-up.** Filtered the polling dashboard by the selected caregiver's current assignments. The Compose build passed strict TypeScript and Vite. In Edge, a simulated reassignment in the dashboard response moved the alert into Sam's selected inbox on polling and out of Alex's inbox. The prior PostgreSQL worker test covers the actual deadline transition.

**2026-11-07 — M3 handoff.** All seven failure-recovery and data-quality criteria passed. See the M3 verification table for commands, reconciliation counts and recovery evidence. Changes are uncommitted at the user's request. The next planned milestone is M4, pending separate authorization.

**2026-11-07 — M3 commit authorization.** The user subsequently authorized committing the completed M3 implementation, tests and documentation. Verification evidence remains recorded above. M4 awaits separate authorization.

**2026-11-07 — M4 handoff.** Inspected the approved documents and actual code, recorded the detailed implementation plan, then completed all five M4 criteria. Evidence is in the M4 table above. The regular dashboard runs migration `0007_context` with persistent data preserved. All work remains uncommitted as requested. No open M4 failures or blockers. The next planned milestone is M5 lifecycle completion, which requires separate authorization; no next-milestone work was started.

**2026-11-07 — M4 commit authorization.** The user subsequently authorized committing the completed M4 implementation, tests, and documentation locally, with no push. The verification evidence above remains applicable; the pre-commit diff check passed. No additional milestone work was authorized.

**2026-11-07 — M5 handoff.** Completed all six M5 criteria and the caregiver primary timeout → backup acknowledgement → recovery → resolution demonstration. Final evidence: 83 backend tests, six simulator tests, strict TypeScript/build, M5 browser/restart/lost-response checks and M4 browser regression passed. Saved lifecycle history and response timing survive restart. The regular dashboard runs at port 8010 with persistent volumes preserved. No open failures or blockers; all M5 changes remain uncommitted. The next planned step is M6, requiring separate authorization; no M6 or M7 implementation was started.

**2026-11-07 - M5 commit authorization.** The user authorized committing the completed M5 implementation, tests and documentation locally, with no push. The verification evidence above remains applicable; the pre-commit diff check passed. No further milestone work was authorized.

**2026-11-07 — M6 handoff.** The user approved the plan before edits. Completed all five M6 criteria with post-commit live hints, REST reconciliation, polling fallback, cached/unknown status, retained mutation retries and chart/keyboard improvements. Evidence: 92 backend tests, six simulator tests, strict TypeScript/build, the full M6 transport/mutation/staleness/keyboard/restart browser suite, M4 chart/context regression and M5 caregiver lifecycle/restart regression passed. Measured reading updates were 913–985 ms in the final run; alert and observation updates were also under two seconds. Documentation/UTF-8 and all 22 local links passed, as did the diff check. M5 remains complete with its prior commit preserved. Main dashboard is healthy at port 8010 with existing volumes intact; M6 fixtures are stopped with evidence retained. No open M6 failures or blockers. All M6 changes are uncommitted at the user's request. M7 was not started and requires separate authorization; no next milestone is authorized.

**2026-11-07 — Dashboard redesign handoff.** Implemented the approved Bubble-inspired single page with reusable React components, a searchable patient roster, snapshot metrics and reading quality, and one patient selection for vitals and observations. The system health panel and demo caregiver picker use the existing endpoints and selection rules. The redesign changes the frontend, browser checks, and documentation.

| Check run | Observed result |
|---|---|
| `docker compose -p wardzero-ui-design-check up -d --build --wait` with `APP_PORT=0` | Isolated stack healthy. Strict TypeScript and Vite production build passed. Vite reported the existing directive and chunk-size warnings. |
| `node scripts/test-context-ui.cjs` and `node scripts/test-lifecycle-ui.cjs` | Passed chart and trend evidence, observation capture and retry, escalation, acknowledgement, resolution, and restart checks against isolated PostgreSQL fixtures. Primary timeout processed 618 ms after the saved deadline. |
| `node scripts/test-realtime-ui.cjs` | Passed transport interruption, missed-alert reconciliation, WebSocket-only polling fallback, heartbeat loss, restart, retained mutation retries, and stale/unknown rendering. Reading updates rendered in 851–898 ms, alert in 926 ms, and observation clear in 68 ms. |
| `node scripts/test-dashboard-ui.cjs` against the isolated stack and regular demo | Edge passed at 1440, 1024, 768, and 375 px. Chart widths were 725, 455, 433, and 325 px at 250 px high. The donut rendered, the page fit without horizontal overflow, and keyboard navigation, search/clear, shared patient selection, REST-derived counts, and the stored vital check passed. The regular demo had two active alerts during the count comparison. Inspected full desktop and phone renders from the isolated stack. |
| `docker compose up -d --build --wait app`, `docker compose exec -T app alembic current`, and `docker compose -p wardzero-ui-design-check down` | Regular dashboard healthy at port 8010. Alembic reported `0008_resolution (head)`. Database and simulator container IDs and named volume mounts matched before and after. Isolated services stopped with their evidence volumes retained. |

The local Markdown check verified 22 links and anchors, the frontend and documentation decoded as UTF-8, and `git diff --check` passed. The redesign is ready for review in the working tree. M7 remains pending and requires separate authorization.

**2026-11-08 — Patient selection usability follow-up.** Placed the roster before the charts and added an explicit Review patient action with keyboard focus on the chart. The roster marks the selected row, both patient panels share the selection, and the observation form identifies the patient and demo caregiver. Selection persists on reload in the same tab. Added direct links to the observation form and caregiver inbox.

| Check run | Observed result |
|---|---|
| `docker compose -p wardzero-patient-selection-check up -d --build --wait --wait-timeout 120` | Strict TypeScript and Vite production build passed, with the existing Vite warnings. |
| `node scripts/test-dashboard-ui.cjs` against the isolated stack and `http://127.0.0.1:8010` | Edge passed at 1440, 1024, 768, and 375 px without horizontal overflow. Desktop keyboard and phone-width pointer checks verified the selected row, synchronized selectors, observation target, and reload persistence. Inspected desktop and phone screenshots. |
| `node scripts/test-context-ui.cjs` and `node scripts/test-realtime-ui.cjs` | Both passed against isolated PostgreSQL fixtures. Verified observation attribution and retry, caregiver actions and history, live updates, staleness, and transport/restart recovery. Reading updates rendered in 926–993 ms. |
| `docker compose up -d --build --wait app` and `docker compose -p wardzero-patient-selection-check down` | Regular app is healthy on port 8010 with the same database and simulator containers and volume mounts. Isolated services stopped with evidence retained. |

The usability update is ready for review in the working tree. M7 remains pending.

**2026-11-08 — Sidebar scroll follow-up.** The sidebar now highlights the section in view while scrolling. Direct links retain their anchor and focus behavior. The isolated `docker compose -p wardzero-sidebar-check up -d --build --wait` passed TypeScript and Vite. `node scripts/test-dashboard-ui.cjs` passed on the isolated and regular stacks. At 1440 and 375 px the highlight followed all six sections through System health and returned to Overview without changing the URL or keyboard focus. Section link checks passed at all four viewport widths. `docker compose up -d --build --wait app` left the regular app healthy at port 8010, and the isolated services were stopped with volumes retained. The fix is ready for review in the working tree.

**2026-11-08 — Pre-M7 risk display handoff.** The roster and saved inbox evidence show Low, Medium, High, or Unknown with a plain-language reason. The roster retains separate data quality and timestamped last-known concern. The inbox continues to show each alert's saved peak priority separately. The display uses the existing assessment payload. English note suggestions were deferred during planning.

| Check run | Observed result |
|---|---|
| `docker compose -p wardzero-prem7-risk-check up -d --build --wait --wait-timeout 120` with `APP_PORT=0` | Isolated stack healthy. Strict TypeScript and Vite passed with the existing directive and chunk-size warnings. |
| `docker compose -p wardzero-prem7-risk-check exec -T app python -m pytest -q` | All 92 tests passed on PostgreSQL with the existing Starlette warning. Extended assertions verified the dashboard contract for incomplete High, observation-only Watch, and current Watch alongside a saved High alert peak. |
| `node scripts/test-dashboard-ui.cjs` against the isolated loopback port | Edge passed at 1440, 1024, 768, and 375 px. Risk labels and reasons were visible with no horizontal overflow. Reviewed the desktop and phone screenshots. |
| `node scripts/test-quality-ui.cjs wardzero-prem7-risk-check` | Passed stale and last-known display, monitoring-gap recovery after reconnect, delivery delay, and historical review across reload. With both Watch and High findings in an incomplete reading, the reason described the High finding. |
| `node scripts/test-context-ui.cjs` | Passed trend, combination and observation-only reasons, opening and latest evidence, separate peak priority, observation attribution, lost-response retry, and restart expiry. |
| `node scripts/test-lifecycle-ui.cjs` and `node scripts/test-realtime-ui.cjs` | Passed escalation, acknowledgement, resolution, saved history, retry, transport and restart regressions, and cached, incomplete, stale and last-known risk display. Reading updates rendered in 967–1367 ms. |

The isolated stacks were stopped with their evidence volumes retained. All 22 local Markdown links and anchors, JavaScript syntax checks, and `git diff --check` passed. The display is ready for review in the working tree. M7 remains pending and requires separate authorization.

**2026-11-08 — Live risk display deployment.** Rebuilt the regular app with `docker compose up -d --build --no-deps --wait --wait-timeout 120 app`. It was healthy on port 8010. The database and simulator container IDs and volume mounts matched before and after. `node scripts/test-dashboard-ui.cjs http://127.0.0.1:8010` verified visible risk labels and reasons at 1440, 1024, 768, and 375 px, alongside the existing dashboard checks.

**2026-11-08 — Five-state risk progression.** The user chose one distinct Watch signal for Low and two or more for Medium. A complete assessment without a firing rule displays No risk, existing High findings display High, and unavailable evidence displays Unknown. The demo trigger now emits one Low, two Medium, and three High samples before returning to baseline. PostgreSQL rules and alert priorities retain their original behavior.

`python -B -m unittest discover -s simulator -p 'test_*.py'` passed all six simulator tests after an authorized rerun outside the Windows sandbox resolved temporary SQLite directory access. The isolated `node scripts/test-realtime-ui.cjs` verified No risk → Low → Medium → High, Unknown, timestamps, and transport recovery. `node scripts/test-context-ui.cjs` passed the saved evidence, observation and retry checks. Rebuilt the live app and simulator with `docker compose up -d --build --no-deps --wait --wait-timeout 120 app simulator`. The PostgreSQL container and both volume mounts matched before and after. `node scripts/test-dashboard-ui.cjs http://127.0.0.1:8010` passed all four viewport checks. M7 remains pending.

**2026-11-08 — Pending risk alert visibility.** The roster keeps a saved open risk alert and its assigned caregiver visible when current readings recover. The indicator follows primary-to-backup escalation and clears after the assigned caregiver acknowledges. The isolated `node scripts/test-lifecycle-ui.cjs` verified normal readings, reload, real escalation (401 ms after the deadline), backup acknowledgement, resolution and restart recovery. Rebuilt the regular app with `docker compose up -d --build --no-deps --wait --wait-timeout 120 app`. The database and simulator container IDs matched before and after. The live `node scripts/test-dashboard-ui.cjs http://127.0.0.1:8010` passed at 1440, 1024, 768 and 375 px. M7 remains pending.

**2026-11-08 — Single retained risk label and caregiver role names.** The roster now displays the strongest assessment saved in the current unacknowledged response cycle in its existing risk badge. After acknowledgement it displays the current assessment. Migration `0009_caregiver_labels` updates the two seeded display names to Primary caregiver and Backup caregiver while preserving their IDs and prior attribution.

The full PostgreSQL suite passed 93 tests via `docker compose -p wardzero-pending-risk-check exec -T app python -m pytest -q`. It covered Medium retention through a lower finding and normal readings, acknowledgement, and a new response cycle. `node scripts/test-lifecycle-ui.cjs` passed the single High badge through recovery, reload, escalation (269 ms after deadline), acknowledgement, resolution, and restart. `node scripts/test-context-ui.cjs` passed the observation and saved evidence regression. The first `node scripts/test-realtime-ui.cjs` run used a patient with an open observation alert for its Unknown assertion. The rerun used a patient whose alert had been resolved and passed progression, caching, polling, staleness, reconnection and restart checks. The app-only live rebuild applied `0009_caregiver_labels (head)` with the same PostgreSQL and simulator containers. The live dashboard returned both role names and passed `node scripts/test-dashboard-ui.cjs http://127.0.0.1:8010` at all four widths. JavaScript syntax checks and `git diff --check` passed. M7 remains pending.

**2026-11-08 — Caregiver inbox bug fixes.** The user authorized three corrections: retain active escalated alerts in the primary inbox, sort newest first, and refresh alerts live. Active inbox filtering now includes the patient's primary caregiver as well as the current assignee. Only the assignee can acknowledge/resolve. Cards show their response-cycle opening/reopening time and sort by that time descending with ID tie-breaking. Query-family refreshes run independently so a stalled history fetch cannot block later dashboard/inbox hints; follow-up hints within each family remain serialized. Existing changes were preserved; no migration or dependency was added.

Acceptance and executed evidence:

| Check run | Observed result |
|---|---|
| `node scripts/test-lifecycle-ui.cjs` | Passed on isolated PostgreSQL: primary retained the escalated card with disabled acknowledgement; backup acknowledged and resolved; new and reopened episodes moved to the first position without reload. Real escalation lag was 521 ms. Saved history, lost-response retry and restart recovery passed. |
| `node scripts/test-realtime-ui.cjs` | Passed with a deliberately blocked history response while subsequent risk/alert updates rendered without refresh. Alert latency was 916 ms; reading updates were 844–919 ms. Real transport interruption, polling fallback, heartbeat loss, cached/stale states, mutation retries and app restart passed. No browser page errors. |
| `docker compose exec -T app python -m pytest -q` | 93 passed on disposable real PostgreSQL databases; one existing Starlette deprecation warning. An earlier attempt in the lifecycle fixture was interrupted by that fixture's intentional app stop, so the complete suite was rerun separately. |
| Browser fixture image builds and `docker compose up -d --build --no-deps --wait --wait-timeout 120 app` | TypeScript and production build passed; regular app rebuilt and healthy on port 8010. Database and simulator services were not recreated; persistent volumes retained. |
| `node scripts/test-dashboard-ui.cjs http://127.0.0.1:8010` | Passed at 1440, 1024, 768 and 375 px, including layout, sidebar, selections, REST counts and stored vitals. |
| `node --check` for both changed browser scripts, local Markdown verification, `git diff --check` | Passed syntax, all 22 local links/anchors and whitespace checks. |

The first realtime run passed the new live-update check but failed an old expected history count after the added fixture reading; correcting the count from two to three produced the passing full run above. Both isolated browser stacks stopped with evidence volumes retained. No outstanding blockers. Changes remain uncommitted. Next step is user review of these fixes; M7 remains pending and requires separate authorization.

**2026-11-08 — M7 verification handoff.** Implemented persistent simulator scenarios, the acceptance runner, the complete recorded browser demo, source snapshot packaging, documentation verification and the [demo runbook](DEMO_RUNBOOK.md). After consultation on the initial test-script caregiver-selection issue, the authorized full rerun passed all 19 checks, 93 PostgreSQL-backed tests, seven simulator tests, frontend build/typecheck, all selected browser regressions and two fresh complete demos. Both demos reconciled 171/171 IDs after the outage and 186/186 at completion, retained exact resolved state/history across restart, and produced inspected backup MP4s. All details and commands are in the M7 evidence table; the machine-readable report and logs are in `artifacts/m7/full-verification/`.

Final review verified Python/JavaScript syntax, all 28 local Markdown links/anchors, `git diff --check`, playable recordings and exclusion of secrets/generated data from the source archive. Packaging twice produces the same source ZIP SHA-256; the final archive path, hashes and comparison against the tested source are saved in `artifacts/m7/full-verification/submission.json`. Application and test-script contents match the acceptance-start snapshot; only documentation changed afterward. The isolated services are stopped with evidence volumes retained. The existing regular demo stack and prior uncommitted changes remain intact.

M7's first five acceptance items are complete. The backup recording portion of the sixth item is complete, but the **Git-tag portion remains pending by the user's explicit choice**. No other failed check or implementation blocker remains. No commit, tag or push was made. The next action is user review; completing the remaining tagged submission requires separate commit/tag authorization. No later milestone or optional P1 work is authorized or started.

**2026-11-08 — Judge-demo readiness spot check.** `git rev-list --left-right --count HEAD...origin/main` returned `0 0` at `e503855`. The committed history contains M0 through M6. The M7 scenario and rehearsal files and later dashboard changes are local working-tree changes. `docker compose ps` and `GET /health/ready` confirmed the regular dashboard was ready on port 8010. Two `GET /api/v1/dashboard` snapshots six seconds apart showed fresh, advancing reading IDs for all three patients and two existing active alerts. `docker compose exec -T app alembic current` reported `0009_caregiver_labels (head)`. The read-only `node scripts/test-dashboard-ui.cjs http://127.0.0.1:8010` passed at 1440, 1024, 768 and 375 px. `docker compose exec -T simulator python -m simulator.recovery status` reported accepted frames with zero pending or quarantined frames. The running simulator returned `No module named simulator.scenario` for `python -m simulator.scenario --help`.

The saved acceptance report records 19/19 successful checks and two complete rehearsals. The SHA-256 of the exact tested source ZIP matches the report. The full suite was not rerun during the spot check. `git diff --check` passed. After the concurrent README and documentation update, `python scripts/check-docs.py` passed all 39 local links and anchors. For a clean judge rehearsal, start a fresh Compose project from the tested source snapshot and build both the app and simulator. The regular demo services and volumes were left in place. The Git-tag criterion remains pending.

**2026-11-08 — Hackathon deliverables preparation.** Rewrote the project README, added the private-value configuration template, updated the runbook and architecture references, and prepared the [standalone technical report](TECHNICAL_DOCUMENTATION.md) with four cropped captures from the recorded verification. The source ZIP includes the template and report figures. Application code, migrations, simulator behavior, dependency lockfiles, and test logic match the verified source byte for byte. The packaging helper adds the template to the archive allowlist.

| Preparation check | Result |
|---|---|
| Extracted source and README PowerShell quick start | In isolated Compose project `wardzero-deliverables-814b247486`, the setup generated private values and preserved them on rerun. An initial harness invocation failed before startup when an empty Compose environment override was supplied. The corrected run passed `docker compose config -q`, build, and startup with fresh volumes. The app bound to loopback, readiness reported ready, and `alembic current` reported `0009_caregiver_labels (head)`. |
| Dashboard and API smoke check | The loopback dashboard API returned three patients with fresh readings. The OpenAPI route inventory matched the documented endpoints. `node scripts/test-dashboard-ui.cjs <isolated-url>` passed at 1440, 1024, 768, and 375 px. The isolated stack was stopped with both evidence volumes retained. See `artifacts/deliverables-smoke.json`. |
| Documentation and package | `python -B scripts/check-docs.py` and `git diff --check` passed. The Mermaid flowchart rendered in Edge, and the four figures were visually checked against the saved captures. Two packaging runs produced the same archive hash. The 106-file manifest matches the working tree, with no runtime or test changes from the tested baseline. See `artifacts/deliverables-verification.json`. |

The smoke check is separate from the full acceptance run documented above. Publication was authorized in separate feature, rehearsal, and documentation commits. The rewritten README remains local. The Git-tag criterion stays pending.
