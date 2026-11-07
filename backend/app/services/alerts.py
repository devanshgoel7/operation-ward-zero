import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.models.alerts import Alert, AlertDetail, AlertPage, Status
from app.models.monitoring import Reading, ReadingInput
from app.services.context import CONTEXT_VERSION, active_observations, observation_findings, trend_readings
from app.services.trends import evaluate_trends
from app.services.errors import MonitoringError
from app.services.quality import FRESHNESS, record_quality
from app.services.risk import RULE_VERSION, threshold_findings


async def assess_reading(conn: AsyncConnection, reading: ReadingInput, patient_id: UUID,
                         received_at: datetime, newest: bool) -> UUID:
    current = newest and received_at - reading.observed_at <= FRESHNESS
    return await assess_context(conn, patient_id, reading, received_at, current)


async def assess_context(conn: AsyncConnection, patient_id: UUID, reading: Reading | None,
                         now: datetime, current: bool = True, trigger: str = "reading",
                         observation_id: UUID | None = None, quality: str | None = None) -> UUID:
    """Caller holds the patient lock; every consequence commits with its trigger."""
    findings, complete = threshold_findings(reading) if reading else ([], False)
    summaries = []
    if current:
        observations = await active_observations(conn, patient_id, now)
        if reading:
            summaries, trends = evaluate_trends(await trend_readings(conn, patient_id, reading.observed_at),
                                                reading.observed_at)
            findings.extend(trends)
        else:
            summaries, _ = evaluate_trends([], now, current=False)
        findings.extend(observation_findings(observations, findings))
        await conn.execute(text("UPDATE patients SET context_expires_at=:expiry WHERE id=:patient"),
                           {"patient": patient_id, "expiry": min((o.expires_at for o in observations), default=None)})
    concern = "none" if complete else None
    if findings:
        concern = "high" if any(f.priority == "high" for f in findings) else "watch"
    values = {
        "patient_id": patient_id, "reading_id": reading.reading_id if reading else None,
        "scope": "current" if current else "historical", "concern": concern,
        "quality": quality or ("fresh" if complete else "incomplete"),
        "version": CONTEXT_VERSION if current else RULE_VERSION,
        "findings": json.dumps([f.model_dump(mode="json") for f in findings]),
        "trends": json.dumps([s.model_dump(mode="json") for s in summaries]),
        "trigger": trigger, "observation": observation_id, "now": now,
    }
    assessment_id = await conn.scalar(text("""
        INSERT INTO assessments (patient_id, reading_id, scope, concern, data_quality, rule_version, findings,
                                 trend_summary, trigger_kind, observation_id, evaluated_at)
        VALUES (:patient_id, :reading_id, :scope, :concern, :quality, :version, CAST(:findings AS jsonb),
                CAST(:trends AS jsonb), :trigger, :observation, :now)
        RETURNING id
    """), values)
    values["assessment_id"] = assessment_id
    if trigger == "reading":
        await record_quality(conn, patient_id, reading.observed_at, now, complete, current, assessment_id)
    if findings:
        await update_concern_episode(conn, patient_id, assessment_id, concern, "risk" if current else "delayed_review")
    elif current:
        # Show removed contributions without resolving or changing the episode's peak.
        await conn.execute(text("""WITH changed AS (
            UPDATE alerts SET latest_assessment_id=:assessment_id,revision=revision+1
            WHERE patient_id=:patient_id AND kind='risk' AND status IN ('open','acknowledged')
              AND (:trigger<>'reading' OR EXISTS (
                SELECT 1 FROM patients p JOIN assessments a ON a.id=p.current_assessment_id,
                    jsonb_array_elements(a.findings) finding
                WHERE p.id=:patient_id AND jsonb_array_length(coalesce(finding->'observations','[]'::jsonb))>0
              )) RETURNING id
        ) INSERT INTO alert_events (alert_id,event_type,assessment_id)
          SELECT id,'updated',:assessment_id FROM changed"""), values)
    if current:
        if concern is not None:
            await conn.execute(text("UPDATE patients SET last_known_assessment_id=:assessment_id WHERE id=:patient_id"),
                               values)
        await conn.execute(text("UPDATE patients SET current_assessment_id = :assessment_id WHERE id = :patient_id"),
                           values)
    return assessment_id


async def update_concern_episode(conn: AsyncConnection, patient_id: UUID, assessment_id: UUID,
                              concern: str, kind: str) -> None:
    # The caller holds the patient lock for the entire ingestion transaction.
    values = {"patient_id": patient_id, "assessment_id": assessment_id, "concern": concern, "kind": kind}
    values["seconds"] = 30 if concern == "high" else 60
    existing = (await conn.execute(text("""
        SELECT a.*, p.primary_caregiver_id, CASE WHEN a.kind='risk' THEN prev.concern ELSE evidence.concern END AS previous_concern
        FROM patients p JOIN alerts a ON a.patient_id=p.id
        LEFT JOIN assessments prev ON prev.id=p.current_assessment_id
        LEFT JOIN assessments evidence ON evidence.id=a.latest_assessment_id
        WHERE p.id=:patient_id AND a.kind=:kind AND a.status IN ('open','acknowledged')
    """), values)).mappings().one_or_none()
    if existing is None:
        alert_id = await conn.scalar(text("""
            INSERT INTO alerts (patient_id, kind, status, peak_priority, assignee_id,
                                original_assessment_id, latest_assessment_id, escalation_due_at)
            SELECT id, :kind, 'open', :concern, primary_caregiver_id, :assessment_id, :assessment_id,
                   now() + make_interval(secs => :seconds)
            FROM patients WHERE id = :patient_id RETURNING id
        """), values)
        event_type = "opened"
    else:
        alert_id = existing["id"]
        reopened = existing["status"] == "acknowledged" and (
            existing["previous_concern"] == "none" or
            (existing["previous_concern"] == "watch" and concern == "high"))
        event_type = "reopened" if reopened else "updated"
        if reopened:
            await conn.execute(text("""
                UPDATE alerts SET status='open', acknowledged_at=NULL, acknowledged_by=NULL,
                    assignee_id=:primary, escalation_due_at=now()+make_interval(secs => :seconds)
                WHERE id=:id
            """), values | {"id": alert_id, "primary": existing["primary_caregiver_id"]})
        await conn.execute(text("""
            UPDATE alerts SET latest_assessment_id=:assessment_id, revision=revision+1,
                escalation_due_at=CASE WHEN escalation_due_at IS NOT NULL
                    THEN least(escalation_due_at, now()+make_interval(secs => :seconds)) END,
                peak_priority=CASE WHEN peak_priority='high' THEN 'high' ELSE :concern END
            WHERE id=:id
        """), values | {"id": alert_id})
    await conn.execute(text("""
        INSERT INTO alert_events (alert_id, event_type, assessment_id)
        VALUES (:alert_id, :event_type, :assessment_id)
    """), values | {"alert_id": alert_id, "event_type": event_type})


ALERT_COLUMNS = "a.*, to_jsonb(first_a) AS original_assessment, to_jsonb(last_a) AS latest_assessment"
ALERT_FROM = """
    FROM alerts a LEFT JOIN assessments first_a ON first_a.id = a.original_assessment_id
    LEFT JOIN assessments last_a ON last_a.id = a.latest_assessment_id
"""


async def list_alerts(conn: AsyncConnection, patient_id: UUID | None = None,
                      assignee_id: UUID | None = None, status: Status | None = None,
                      cursor: str | None = None, limit: int = 50, active_only: bool = False) -> AlertPage:
    query = f"SELECT {ALERT_COLUMNS} {ALERT_FROM} WHERE TRUE"
    if active_only:
        query += " AND a.status IN ('open','acknowledged')"
    values = {"count": limit + 1}
    for column, value in (("patient_id", patient_id), ("assignee_id", assignee_id), ("status", status)):
        if value is not None:
            query += f" AND a.{column} = :{column}"
            values[column] = value
    if cursor is not None:
        try:
            stamp, identifier = cursor.split("|")
            boundary = datetime.fromisoformat(stamp)
            if boundary.tzinfo is None:
                raise ValueError()
            values.update(stamp=boundary, identifier=UUID(identifier))
        except ValueError as exc:
            raise MonitoringError(422, "invalid_cursor", "Invalid alert cursor.") from exc
        query += " AND (a.opened_at, a.id) < (:stamp, :identifier)"
    rows = await conn.execute(text(query + " ORDER BY a.opened_at DESC, a.id DESC LIMIT :count"), values)
    alerts = [Alert.model_validate(row) for row in rows.mappings()]
    next_cursor = None
    if len(alerts) > limit:
        alerts.pop()
        next_cursor = f"{alerts[-1].opened_at.isoformat()}|{alerts[-1].id}"
    return AlertPage(items=alerts, next_cursor=next_cursor)


async def alert_detail(conn: AsyncConnection, alert_id: UUID) -> AlertDetail:
    row = (await conn.execute(text(f"""
        SELECT {ALERT_COLUMNS}, (
            SELECT jsonb_agg(to_jsonb(e) ORDER BY e.occurred_at, e.id)
            FROM alert_events e WHERE e.alert_id = a.id
        ) AS events
        {ALERT_FROM} WHERE a.id = :id
    """), {"id": alert_id})).mappings().one_or_none()
    if row is None:
        raise MonitoringError(404, "unknown_alert", "Alert does not exist.")
    return AlertDetail.model_validate(row)


async def acknowledge(engine: AsyncEngine, alert_id: UUID, actor: UUID, command_id: UUID) -> Alert:
    values = {"id": alert_id, "actor": actor, "command": command_id}
    async with engine.begin() as conn:
        patient_id = await conn.scalar(text("""
            SELECT p.id FROM patients p JOIN alerts a ON a.patient_id = p.id WHERE a.id = :id FOR UPDATE OF p
        """), values)
        if patient_id is None:
            raise MonitoringError(404, "unknown_alert", "Alert does not exist.")
        alert = (await conn.execute(text("SELECT status, assignee_id FROM alerts WHERE id = :id"), values)).one()
        if alert.assignee_id != actor:
            raise MonitoringError(403, "wrong_assignee", "Only the assigned demo caregiver can acknowledge.")
        # Reserve the global command ID before changing state. A rejected transition rolls it back.
        occurred = await conn.scalar(text("""
            INSERT INTO alert_events (alert_id, event_type, caregiver_id, command_id)
            VALUES (:id, 'acknowledged', :actor, :command)
            ON CONFLICT (command_id) DO NOTHING RETURNING occurred_at
        """), values)
        if occurred is None:
            replay = await conn.scalar(text("""
                SELECT 1 FROM alert_events WHERE command_id = :command AND alert_id = :id
                    AND caregiver_id = :actor AND event_type = 'acknowledged'
            """), values)
            if not replay:
                raise MonitoringError(409, "command_conflict", "Command ID already used for another action.")
        else:
            if alert.status != "open":
                raise MonitoringError(409, "already_acknowledged", "Alert has already been acknowledged.")
            await conn.execute(text("""
                UPDATE alerts SET status = 'acknowledged', acknowledged_by = :actor,
                    acknowledged_at = :occurred, escalation_due_at=NULL, revision = revision + 1 WHERE id = :id
            """), values | {"occurred": occurred})
        updated = (await conn.execute(text(f"SELECT {ALERT_COLUMNS} {ALERT_FROM} WHERE a.id = :id"),
                                      values)).mappings().one()
        return Alert.model_validate(updated)


async def escalate_due(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        patients = await conn.scalars(text("""
            SELECT p.id FROM patients p WHERE EXISTS (SELECT 1 FROM alerts a WHERE
                a.patient_id=p.id AND a.status='open' AND a.escalation_due_at <= now())
            ORDER BY p.id FOR UPDATE
        """))
        for patient_id in patients:
            await conn.execute(text("""
                WITH moved AS (
                    UPDATE alerts a SET assignee_id=p.backup_caregiver_id, escalation_due_at=NULL,
                        revision=revision+1 FROM patients p WHERE p.id=:patient AND a.patient_id=p.id
                        AND a.status='open' AND a.escalation_due_at <= now() RETURNING a.id, a.assignee_id
                ) INSERT INTO alert_events (alert_id,event_type,caregiver_id)
                  SELECT id,'escalated',assignee_id FROM moved
            """), {"patient": patient_id})
