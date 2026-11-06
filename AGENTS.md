# Operation Ward Zero development instructions

## Start here

Read this file, then [architecture](docs/ARCHITECTURE.md), [implementation progress](docs/IMPLEMENTATION_PLAN.md), and [decisions](docs/DECISIONS.md). These documents preserve the approved planning baseline. Inspect actual files and current user instructions before acting.

The project is a solo hackathon prototype with a 48-development-hour budget. The developer is stronger in Python than React. Optimize for a working, understandable, demonstrable application.

The current authorized deliverable is persistent documentation. Application implementation begins when the user requests it. The roadmap records planned work and must never be treated as evidence that a feature already exists.

## Product objective and scope

Demonstrate simulated patient monitoring through durable ingestion, explainable assessment, saved alerts, caregiver acknowledgement, escalation, and resolution. Demonstrate real network interruption and recovery with identifier-based verification.

Use three fictional adult patients and two seeded demo caregivers. Run locally through Docker Compose. Implement threshold rules, two historical trends, and structured caregiver observations.

Advanced ML, LLMs, predictive analytics, attendance tracking, real authentication, external messaging, hardware, public hosting, and multi-organization support are outside the approved initial scope. Preserve this strategic selection unless the user changes it.

## Development workflow

1. Read the current milestone and inspect existing implementation.
2. Implement one logical feature at a time within the authorized milestone.
3. Run its acceptance tests and relevant regression checks.
4. Review the result and update documentation and progress with actual evidence.
5. Commit coherent feature work as authorized in the working session.
6. Advance only after the current milestone works and the user's authorized scope permits it.

Preserve working interfaces and user changes. Avoid unnecessary rewrites, premature abstractions, and unrelated cleanup. Use meaningful names, Python type annotations, strict TypeScript, explicit validation, and clear error handling. Pin compatible dependencies and maintain lockfiles when implementation begins.

Keep architecture changes synchronized across the architecture, decision log, and affected acceptance criteria. Routine implementation choices can be resolved within the approved design. Explain material changes and their implications before expanding scope.

## Engineering invariants

- Commit generated readings to the simulator's persistent SQLite buffer before upload.
- Acknowledge ingestion only after PostgreSQL commits the reading, assessment, alert changes, and audit events together.
- Reuse stable identifiers on retries. Enforce uniqueness in PostgreSQL.
- Store observation time separately from receipt time. Historical input cannot move current state backwards.
- Represent data quality separately from concern. Missing or stale data must remain visible.
- Save alert deadlines and transitions in PostgreSQL. Recover overdue work after restart.
- Treat WebSocket messages as update hints. Restore authoritative state through REST queries.
- Use one FastAPI worker and one periodic loop for this prototype.
- Preserve pending/quarantined readings and report persistence failures visibly.
- Use genuine service or transport failures in the reliability demonstration.

## Testing and reporting

Every feature requires appropriate tests and explicit acceptance criteria. Use real PostgreSQL for transaction, constraint, concurrency, and restart tests. Use deterministic scenarios and a controllable clock for rules and deadlines. Retain polling while adding WebSockets.

Document exact checks run and their outcomes. Mark unexecuted checks as pending. Never infer success from code presence. Documentation-only work needs content/link verification rather than application scaffolding or dependency installation.

At handoff, record completed work, failures or blockers, the next authorized step, and test evidence in IMPLEMENTATION_PLAN.md. Keep milestone status accurate.

## Safety and demo boundaries

Use synthetic data only. Label rule parameters and accelerated deadlines as demonstration settings. Describe findings as explainable concern levels without diagnoses or clinically validated predictions. The demo caregiver selector supplies attribution and offers no production identity assurance.

Bind published application ports to loopback. Keep simulator keys out of the frontend and source control. Preserve persistent volumes on ordinary startup. Any reset procedure must be explicit.

## Repository conventions

The planned application areas are backend/, frontend/, simulator/, config/, scripts/, and tests/e2e/. Create them incrementally with their milestones. The four persistent documents already define the baseline. Add README, API/database references, and a demo runbook as their implementation makes them useful.

Avoid microservices, Kubernetes, Kafka, Redis, generic internal message buses, and event-sourcing infrastructure for this scope. Favor direct modules and database transactions.
