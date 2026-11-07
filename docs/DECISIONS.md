# Architectural decisions

Recorded 2026-11-06. All entries below capture the approved planning baseline. Implementation status lives in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). The behavioral contract lives in [ARCHITECTURE.md](ARCHITECTURE.md).

Use stable decision IDs. Record later changes with date, reason, consequences, and the superseded decision. Keep the architecture and affected tests synchronized.

## D01 — Focus on reliability and alert response

Accepted. The user selected a 48-development-hour solo build and confirmed that selected challenges are sufficient. Implement monitoring, durable ingestion, explainable rules, historical trends, observations, and caregiver response. Invest deepest effort in actual recovery and durable alert lifecycle behavior.

Integration, resilience, and practicality together account for 65% of the supplied rubric. Technical skill and explainability are demonstrated through transactions, testable rules, evidence, and completed response workflows. This is a strategy against the supplied criteria, with no guarantee of winning.

## D02 — Defer advanced ML, LLMs, and forecasting

Accepted and reaffirmed by the user. Use explicit thresholds, descriptive trends, and structured observations. Exclude predictive analytics and AI dependencies from initial implementation.

There is no established clinical outcome dataset in scope. Synthetic threshold-generated labels would mainly test reproduction of the generator. Credible forecasting would require defined outcomes, patient/time-separated evaluation, leakage controls, calibration, and baseline comparison. Spend the available time on integration and demonstrable reliability. Describe implemented intelligence accurately as rule-based contextual assessment.

## D03 — Modular monolith with three runtime services

Accepted. Run the FastAPI application, PostgreSQL, and simulator in Docker Compose. Serve the compiled React dashboard from the application. Keep backend responsibilities in direct modules.

The simulator represents an independently operating home device and continues generating during application failure. PostgreSQL supplies durable coordination. Microservices, Kafka, Redis, Kubernetes, and event-sourcing infrastructure are outside this scale and scope.

## D04 — Preserve the preferred stack

Accepted. Use Python/FastAPI/Pydantic, PostgreSQL with SQLAlchemy async and asyncpg, Alembic, React/TypeScript/Vite, TanStack Query, Recharts, WebSockets, and Compose. Pin compatible versions in M0.

This matches the user's Python strength and constrains frontend complexity. SQLAlchemy/Alembic support explicit persistence and incremental schema evolution. Query/chart libraries reduce custom UI infrastructure.

## D05 — Persistent SQLite simulator buffer

Accepted. Commit every generated frame to a named-volume SQLite database before upload. Preserve UUID, sequence, payload, status, and retry metadata. Use explicit transactions and synchronous=FULL.

The buffer survives simulator restart and network failure with a small operational footprint. Upload retries cannot block generation. Quarantined and pending data remain inspectable. Storage failure is surfaced explicitly. Guarantees assume durable storage remains intact.

## D06 — Atomic ingestion and idempotent effects

Accepted. Commit reading, assessment, alert changes, and events in one PostgreSQL transaction before returning success. Use stable reading IDs, unique device sequences, payload comparison, and patient-first row locking.

This closes the crash window between accepting a reading and saving its consequences. Retried transport may repeat requests while database constraints prevent duplicate effects. Conflicting identity reuse returns 409. Caregiver command IDs and observation IDs similarly support safe retries.

## D07 — Separate concern, freshness, and historical evidence

Accepted. Store observation and receipt times separately. Track concern and quality independently. Historical records remain queryable while the current pointer preserves time order.

Old abnormal readings produce aggregated delayed-review evidence. Missing/stale data stays visible. Current trends require sufficient continuous history. Full retrospective trend recomputation is deferred. The system exposes the limitations of available evidence in its explanations.

M3 implementation note, 2026-11-07. Preserve each reading assessment as evidence of what was observed at ingestion. Derive current data quality at query time from observation timestamps, and persist the gap episode and recovery count under the patient lock. This lets a silent monitor become visibly stale without inventing measurements. On upgrade, group existing M2 historical findings into delayed-review episodes while preserving their assessment IDs.

M4 implementation note, 2026-11-07. Trend windows are `(t-120s,t-60s]` and `(t-60s,t]`, anchored to the eligible current reading. Continuity includes outer edges and is checked separately for each metric. Persist complete sample evidence and unsupported-history reasons. Latest-per-tag observations expire at exactly ten minutes; selection precedes expiry filtering so older positives cannot return. Observation capture/expiry creates a new assessment under the patient lock rather than modifying original reading evidence. A partial unique reading-assessment index preserves receipt replay while allowing contextual reassessment of the same reading. Store the next observation expiry on the patient so startup and the existing worker recover due work. Clearing and expiry update current/latest evidence without resolving a risk episode or reducing its historical peak. These choices implement the approved context rules without adding prediction or another worker.

## D08 — Persist alert lifecycle and deadlines

Accepted. Save open/acknowledged/resolved state, assignee, peak priority, deadline, and audit history in PostgreSQL. Keep one active alert per patient and kind. Use a five-second periodic loop and startup recovery.

High/watch deadlines are 30/60-second demonstration settings. Escalate once from primary to backup. Acknowledgement cancels pending escalation. Higher priority requires acknowledgement again. Resolution follows the conditions in the architecture. Restart recovery reads saved state rather than rebuilding in-memory countdowns.

## D09 — One application worker and recoverable live updates

Accepted. Run one Uvicorn worker. Use WebSockets for invalidation, bounded client queues, REST snapshots on reconnect, and polling fallback.

This supports the small demo without shared connection infrastructure. PostgreSQL remains authoritative if notifications are missed. Polling is built first, allowing the workflow to function before realtime polish. Future multi-worker deployment requires a separate coordination design.

## D10 — Local synthetic demonstration and demo identities

Accepted by the user. Use three fictional general-adult patients, two caregiver identities, a visible identity selector, in-app routing, and loopback-bound application access. Protect ingestion with an environment-configured simulator key.

The selector records the chosen demo actor. Production identity assurance and external delivery require future work. Keep keys out of the frontend and source control. Thresholds and short deadlines are demonstration parameters. Avoid diagnostic or clinically validated prediction claims.

## D11 — Evidence-driven incremental delivery

Accepted. Complete independently testable milestones with plan, implementation, testing, review, documentation, and coherent commits. Aim for 40 scheduled hours and reserve eight for contingency.

Deliver durable monitoring by M1 and basic caregiver response by M2. Add resilience, context, escalation, and realtime polish sequentially. Do not spend contingency on optional features while acceptance criteria fail. Use real PostgreSQL for persistence behavior and genuine transport/service interruption for the demo.

## D12 — Retain hackathon evidence

Accepted. Keep readings, assessments, observations, events, and simulator records throughout the hackathon. Ordinary startup preserves state. Use a deliberate documented reset procedure.

Expected data volume fits ordinary PostgreSQL tables. Automatic deletion, partitioning, and real patient retention policies are deferred. Retained records allow identifier reconciliation and inspection of the failure demonstration.
