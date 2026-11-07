"""Gap transitions run under the same patient lock as ingestion."""
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from app.services.realtime import RealtimeHub, notify

FRESHNESS = timedelta(seconds=30)


async def check_gap(conn: AsyncConnection, patient_id: UUID, now: datetime) -> bool:
    values = {"id": patient_id, "now": now, "cutoff": now - FRESHNESS}
    reset = await conn.execute(text("""UPDATE alerts SET recovery_count=0,recovery_observed_at=NULL
        WHERE patient_id=:id AND kind='risk' AND status IN ('open','acknowledged')
          AND recovery_observed_at<:cutoff"""), values)
    overdue = await conn.scalar(text("""SELECT greatest(last_complete_at, monitoring_started_at) < :cutoff
        FROM patients WHERE id=:id"""), values)
    if not overdue:
        return reset.rowcount > 0
    await conn.execute(text("UPDATE patients SET gap_recovery_count=0 WHERE id=:id AND gap_recovery_count>0"), values)
    opened = await conn.execute(text("""
        WITH opened AS (
            INSERT INTO alerts (patient_id, kind, status, peak_priority, assignee_id, escalation_due_at, opened_at,
                                response_started_at)
            SELECT id, 'monitoring_gap', 'open', 'watch', primary_caregiver_id,
                   CAST(:now AS timestamptz) + interval '60 seconds', :now, :now FROM patients WHERE id=:id
            ON CONFLICT (patient_id, kind) WHERE status IN ('open','acknowledged') DO NOTHING RETURNING id
        ) INSERT INTO alert_events (alert_id, event_type, occurred_at) SELECT id, 'opened', :now FROM opened
    """), values)
    return reset.rowcount > 0 or opened.rowcount > 0


async def check_freshness(engine: AsyncEngine, now: datetime, hub: RealtimeHub | None = None) -> None:
    changed = []
    async with engine.begin() as conn:
        patients = await conn.scalars(text("SELECT id FROM patients ORDER BY id FOR UPDATE"))
        for patient in patients:
            if await check_gap(conn, patient, now):
                changed.append(patient)
    for patient in changed:
        notify(hub, "patient.updated", patient_id=patient)
        notify(hub, "alert.updated", patient_id=patient)


async def record_quality(conn: AsyncConnection, patient_id: UUID, observed: datetime, now: datetime,
                         complete: bool, current: bool, assessment_id: UUID) -> None:
    await check_gap(conn, patient_id, now)
    values = {"id": patient_id, "observed": observed, "now": now, "assessment": assessment_id}
    if complete:
        await conn.execute(text("""UPDATE patients SET last_complete_at=greatest(last_complete_at,:observed)
            WHERE id=:id"""), values)
    if not current:
        return
    gap = await conn.scalar(text("""SELECT id FROM alerts WHERE patient_id=:id
        AND kind='monitoring_gap' AND status IN ('open','acknowledged')"""), values)
    if gap is None:
        return
    count = await conn.scalar(text("SELECT gap_recovery_count FROM patients WHERE id=:id"), values)
    count = count + 1 if complete else 0
    if count == 3:
        await conn.execute(text("""UPDATE alerts SET status='resolved', resolved_at=:now,
            escalation_due_at=NULL, revision=revision+1 WHERE id=:gap"""), values | {"gap": gap})
        await conn.execute(text("""INSERT INTO alert_events (alert_id,event_type,assessment_id,occurred_at)
            VALUES (:gap,'resolved',:assessment,:now)"""), values | {"gap": gap})
        count = 0
    await conn.execute(text("UPDATE patients SET gap_recovery_count=:count WHERE id=:id"), values | {"count": count})
