import hashlib
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.models.monitoring import PatientSnapshot, ReadingInput, ReadingPage, Receipt, StoredReading
from app.services.alerts import assess_reading
from app.services.errors import MonitoringError


async def ingest(engine: AsyncEngine, reading: ReadingInput) -> Receipt:
    values = reading.model_dump()
    values["payload_hash"] = hashlib.sha256(reading.model_dump_json().encode()).hexdigest()
    async with engine.begin() as conn:
        patient_id = await conn.scalar(text("""
            SELECT p.id FROM patients p JOIN devices d ON d.patient_id = p.id
            WHERE d.id = :device_id FOR UPDATE OF p
        """), values)
        if patient_id is None:
            raise MonitoringError(422, "unknown_device", "Device is unregistered.")
        values["patient_id"] = patient_id
        received = await conn.scalar(text("""
            INSERT INTO readings (id, patient_id, device_id, sequence, observed_at, heart_rate_bpm,
                                  spo2_pct, systolic_mmhg, diastolic_mmhg, temperature_c, payload_hash)
            VALUES (:reading_id, :patient_id, :device_id, :sequence, :observed_at, :heart_rate_bpm,
                    :spo2_pct, :systolic_mmhg, :diastolic_mmhg, :temperature_c, :payload_hash)
            ON CONFLICT DO NOTHING RETURNING received_at
        """), values)
        if received is None:
            received = await conn.scalar(text("""
                SELECT received_at FROM readings WHERE id = :reading_id AND payload_hash = :payload_hash
            """), values)
            if received is None:
                raise MonitoringError(409, "identity_conflict", "Reading ID or sequence already used.")
            assessment_id = await conn.scalar(
                text("SELECT id FROM assessments WHERE reading_id = :reading_id"), values)
            disposition = "duplicate"
        else:
            newest = await conn.scalar(text("""
                UPDATE patients SET latest_reading_id = :reading_id
                WHERE id = :patient_id AND (latest_reading_id IS NULL OR EXISTS (
                    SELECT 1 FROM readings WHERE id = latest_reading_id
                    AND (observed_at, id) < (:observed_at, :reading_id)
                )) RETURNING id
            """), values)
            assessment_id = await assess_reading(conn, reading, patient_id, received, newest is not None)
            disposition = "accepted"
    return Receipt(reading_id=reading.reading_id, received_at=received, disposition=disposition,
                   assessment_id=assessment_id)


async def snapshots(conn: AsyncConnection, patient_id: UUID | None = None) -> list[PatientSnapshot]:
    query = """
        SELECT to_jsonb(p) || jsonb_build_object('device_id', d.id) AS patient,
               CASE WHEN r.id IS NOT NULL THEN (to_jsonb(r) - 'payload_hash' - 'id')
                    || jsonb_build_object('reading_id', r.id) END AS latest_reading,
               to_jsonb(a) AS current_assessment
        FROM patients p JOIN devices d ON d.patient_id = p.id
        LEFT JOIN readings r ON r.id = p.latest_reading_id
        LEFT JOIN assessments a ON a.id = p.current_assessment_id
    """
    if patient_id is not None:
        query += " WHERE p.id = :patient_id"
    rows = await conn.execute(text(query + " ORDER BY p.id"), {"patient_id": patient_id})
    return [PatientSnapshot.model_validate(row) for row in rows.mappings()]


async def history(conn: AsyncConnection, patient_id: UUID, start: datetime, end: datetime,
                  cursor: str | None, limit: int) -> ReadingPage:
    values = {"patient_id": patient_id, "start": start, "end": end, "count": limit + 1}
    query = """
        SELECT id AS reading_id, device_id, patient_id, sequence, observed_at, received_at,
               heart_rate_bpm, spo2_pct, systolic_mmhg, diastolic_mmhg, temperature_c
        FROM readings WHERE patient_id = :patient_id AND observed_at BETWEEN :start AND :end
    """
    if cursor is not None:
        try:
            timestamp, reading_id = cursor.split("|")
            boundary = datetime.fromisoformat(timestamp)
            if boundary.tzinfo is None:
                raise ValueError()
            values.update(cursor_time=boundary, cursor_id=UUID(reading_id))
        except ValueError as exc:
            raise MonitoringError(422, "invalid_cursor", "Invalid reading history cursor.") from exc
        query += " AND (observed_at, id) < (:cursor_time, :cursor_id)"
    rows = await conn.execute(text(query + " ORDER BY observed_at DESC, id DESC LIMIT :count"), values)
    items = [StoredReading.model_validate(row) for row in rows.mappings()]
    next_cursor = None
    if len(items) > limit:
        items.pop()
        last = items[-1]
        next_cursor = f"{last.observed_at.isoformat()}|{last.reading_id}"
    return ReadingPage(items=items, next_cursor=next_cursor)
