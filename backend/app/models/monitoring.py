from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.alerts import Alert, Assessment
from app.models.observations import Observation


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    reading_id: UUID
    device_id: UUID
    sequence: Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]
    observed_at: AwareDatetime
    heart_rate_bpm: Annotated[float, Field(strict=True, gt=0)] | None
    spo2_pct: Annotated[float, Field(strict=True, ge=0, le=100)] | None
    systolic_mmhg: Annotated[float, Field(strict=True, gt=0)] | None
    diastolic_mmhg: Annotated[float, Field(strict=True, gt=0)] | None
    temperature_c: Annotated[float, Field(strict=True)] | None

    @model_validator(mode="after")
    def validate_measurements(self) -> Self:
        if self.systolic_mmhg is not None and self.diastolic_mmhg is not None:
            if self.systolic_mmhg < self.diastolic_mmhg:
                raise ValueError("Systolic pressure must be at least diastolic pressure.")
        self.observed_at = self.observed_at.astimezone(UTC)
        return self


class ReadingInput(Reading):
    @model_validator(mode="after")
    def validate_time(self) -> Self:
        if self.observed_at > datetime.now(UTC) + timedelta(seconds=5):
            raise ValueError("Observation exceeds the five-second clock allowance.")
        return self


class StoredReading(Reading):
    patient_id: UUID
    received_at: AwareDatetime


class Receipt(BaseModel):
    reading_id: UUID
    disposition: Literal["accepted", "duplicate"]
    received_at: AwareDatetime
    assessment_id: UUID | None


class Caregiver(BaseModel):
    id: UUID
    display_name: str


class Patient(BaseModel):
    id: UUID
    display_name: str
    device_id: UUID
    primary_caregiver_id: UUID
    backup_caregiver_id: UUID


class PatientSnapshot(BaseModel):
    patient: Patient
    latest_reading: StoredReading | None
    current_assessment: Assessment | None
    data_quality: Literal["fresh", "incomplete", "stale", "unavailable"]
    last_known_concern: Literal["none", "watch", "high"] | None
    last_known_observed_at: AwareDatetime | None
    delivery_delayed: bool
    active_observations: list[Observation]


class Dashboard(BaseModel):
    server_time: AwareDatetime
    caregivers: list[Caregiver]
    patients: list[PatientSnapshot]
    active_alerts: list[Alert]


class ReadingPage(BaseModel):
    items: list[StoredReading]
    next_cursor: str | None
