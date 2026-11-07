from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models.alerts import Finding, ReadingEvidence
from app.models.monitoring import Reading
from app.models.observations import Observation

CONTEXT_VERSION = "demo-context-v1"
OBSERVATION_LIFETIME = timedelta(minutes=10)
OBSERVATION_COLUMNS = "id AS observation_id, patient_id, caregiver_id, tag, present, note, created_at, expires_at"


async def active_observations(conn: AsyncConnection, patient_id: UUID, now: datetime) -> list[Observation]:
    rows = await conn.execute(text(f"""SELECT {OBSERVATION_COLUMNS} FROM (
        SELECT DISTINCT ON (tag) * FROM observations WHERE patient_id=:patient
        ORDER BY tag,created_at DESC,ordinal DESC
    ) latest WHERE present AND expires_at>:now ORDER BY tag"""), {"patient": patient_id, "now": now})
    return [Observation.model_validate(row) for row in rows.mappings()]


async def trend_readings(conn: AsyncConnection, patient_id: UUID, end: datetime) -> list[Reading]:
    rows = await conn.execute(text("""SELECT id AS reading_id, device_id, sequence, observed_at,
        heart_rate_bpm,spo2_pct,systolic_mmhg,diastolic_mmhg,temperature_c FROM readings
        WHERE patient_id=:patient AND observed_at>:start AND observed_at<=:end
        ORDER BY observed_at,id"""), {"patient": patient_id, "start": end-timedelta(seconds=120), "end": end})
    return [Reading.model_validate(row) for row in rows.mappings()]


def observation_findings(observations: list[Observation], vital_findings: list[Finding]) -> list[Finding]:
    findings = [Finding(rule_id=f"observation.{o.tag}.watch", priority="watch", metric=o.tag,
        value=1, unit="present", condition="active structured observation", observed_at=o.created_at,
        observations=[o]) for o in observations]
    breathlessness = next((o for o in observations if o.tag == "breathlessness"), None)
    oxygen = [f for f in vital_findings if f.metric == "spo2_pct"]
    if breathlessness and oxygen:
        evidence = {e.reading_id: e for f in oxygen for e in f.evidence}
        for f in oxygen:
            if not f.evidence and f.reading_id is not None:
                evidence[f.reading_id] = ReadingEvidence(reading_id=f.reading_id, observed_at=f.observed_at, value=f.value)
        findings.append(Finding(rule_id="breathlessness.spo2.high", priority="high", metric="spo2_pct",
            value=oxygen[0].value, unit=oxygen[0].unit,
            condition="breathlessness AND (current SpO2 threshold breach OR falling trend)",
            observed_at=oxygen[0].observed_at, reading_id=oxygen[0].reading_id,
            evidence=list(evidence.values()), observations=[breathlessness]))
    return findings
