from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.models.alerts import Assessment, ObservationReceipt
from app.models.monitoring import Reading
from app.models.observations import Observation, ObservationInput
from app.services.alerts import assess_context
from app.services.context import OBSERVATION_COLUMNS, OBSERVATION_LIFETIME
from app.services.errors import MonitoringError
from app.services.quality import FRESHNESS
from app.services.realtime import RealtimeHub, notify


async def reassess(conn: AsyncConnection, patient_id: UUID, now: datetime,
                   trigger: str, observation_id: UUID | None = None) -> UUID:
    row = (await conn.execute(text("""SELECT r.id AS reading_id,r.device_id,r.sequence,r.observed_at,
        r.heart_rate_bpm,r.spo2_pct,r.systolic_mmhg,r.diastolic_mmhg,r.temperature_c,
        greatest(p.last_complete_at,p.monitoring_started_at) AS last_complete
        FROM patients p LEFT JOIN readings r ON r.id=p.latest_reading_id WHERE p.id=:id"""),
        {"id": patient_id})).mappings().one()
    reading = None
    quality = "unavailable"
    if row["reading_id"]:
        quality = "stale"
        if row["observed_at"] >= now-FRESHNESS:
            reading = Reading.model_validate({k: v for k, v in row.items() if k != "last_complete"})
            quality = ("stale" if row["last_complete"] < now-FRESHNESS else
                       "incomplete" if any(getattr(reading, k) is None for k in
                       ("heart_rate_bpm", "spo2_pct", "systolic_mmhg", "diastolic_mmhg", "temperature_c")) else "fresh")
    return await assess_context(conn, patient_id, reading, now, trigger=trigger,
                                observation_id=observation_id, quality=quality)


async def record_observation(engine: AsyncEngine, patient_id: UUID, actor: UUID, body: ObservationInput,
                              now: datetime | None = None, hub: RealtimeHub | None = None) -> tuple[ObservationReceipt, bool]:
    async with engine.begin() as conn:
        patient = (await conn.execute(text("SELECT * FROM patients WHERE id=:id FOR UPDATE"),
                                      {"id": patient_id})).mappings().one_or_none()
        if patient is None:
            raise MonitoringError(404, "unknown_patient", "Patient does not exist.")
        if actor not in (patient["primary_caregiver_id"], patient["backup_caregiver_id"]):
            raise MonitoringError(403, "wrong_caregiver", "Only this patient's primary or backup caregiver can record observations.")
        # Timestamp after locking: concurrent commands are ordered by server acceptance.
        now = now or datetime.now(UTC)
        values = body.model_dump() | {"patient": patient_id, "actor": actor, "now": now,
                                     "expiry": now+OBSERVATION_LIFETIME}
        inserted = await conn.scalar(text("""INSERT INTO observations
            (id,patient_id,caregiver_id,tag,present,note,created_at,expires_at)
            VALUES (:observation_id,:patient,:actor,:tag,:present,:note,:now,:expiry)
            ON CONFLICT (id) DO NOTHING RETURNING id"""), values)
        row = (await conn.execute(text(f"SELECT {OBSERVATION_COLUMNS} FROM observations WHERE id=:observation_id"),
                                  values)).mappings().one()
        observation = Observation.model_validate(row)
        if inserted is None:
            if (observation.patient_id != patient_id or observation.caregiver_id != actor or
                any(getattr(observation, k) != v for k, v in body.model_dump().items())):
                raise MonitoringError(409, "observation_conflict", "Observation ID already used for different content or actor.")
            assessment = (await conn.execute(text("SELECT * FROM assessments WHERE observation_id=:observation_id"),
                                             values)).mappings().one()
        else:
            assessment_id = await reassess(conn, patient_id, now, "observation", body.observation_id)
            assessment = (await conn.execute(text("SELECT * FROM assessments WHERE id=:id"),
                                             {"id": assessment_id})).mappings().one()
        receipt = ObservationReceipt(observation=observation, assessment=Assessment.model_validate(assessment))
    if inserted is not None:
        notify(hub, "patient.updated", patient_id=patient_id)
        notify(hub, "alert.updated", patient_id=patient_id)
    return receipt, inserted is None


async def expire_observations(engine: AsyncEngine, now: datetime, hub: RealtimeHub | None = None) -> None:
    async with engine.begin() as conn:
        patients = (await conn.scalars(text("""SELECT id FROM patients WHERE context_expires_at<=:now
            ORDER BY id FOR UPDATE"""), {"now": now})).all()
        for patient_id in patients:
            await reassess(conn, patient_id, now, "observation_expiry")
    for patient_id in patients:
        notify(hub, "patient.updated", patient_id=patient_id)
        notify(hub, "alert.updated", patient_id=patient_id)
