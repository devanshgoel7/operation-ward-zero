from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.models.observations import Observation

Priority = Literal["watch", "high"]
Status = Literal["open", "acknowledged", "resolved"]


class ReadingEvidence(BaseModel):
    reading_id: UUID
    observed_at: AwareDatetime
    value: float


class TrendSummary(BaseModel):
    metric: str
    unit: str
    start: AwareDatetime
    midpoint: AwareDatetime
    end: AwareDatetime
    status: Literal["calculated", "insufficient_samples", "gap", "not_current"]
    earlier_count: int
    recent_count: int
    earlier_median: float | None = None
    recent_median: float | None = None
    change: float | None = None
    max_gap_seconds: float | None = None
    evidence: list[ReadingEvidence] = Field(default_factory=list)


class Finding(BaseModel):
    rule_id: str
    priority: Priority
    metric: str
    value: float
    unit: str
    condition: str
    reading_id: UUID | None = None
    observed_at: AwareDatetime
    evidence: list[ReadingEvidence] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)


class Assessment(BaseModel):
    id: UUID
    patient_id: UUID
    reading_id: UUID | None
    observation_id: UUID | None = None
    trigger_kind: Literal["reading", "observation", "observation_expiry"] = "reading"
    scope: Literal["current", "historical"]
    concern: Literal["none", "watch", "high"] | None
    data_quality: Literal["fresh", "incomplete", "stale", "unavailable"]
    evaluated_at: AwareDatetime
    rule_version: str
    findings: list[Finding]
    trend_summary: list[TrendSummary] = Field(default_factory=list)


class ObservationReceipt(BaseModel):
    observation: Observation
    assessment: Assessment


class Alert(BaseModel):
    id: UUID
    patient_id: UUID
    kind: Literal["risk", "delayed_review", "monitoring_gap"]
    status: Status
    peak_priority: Priority
    assignee_id: UUID
    opened_at: AwareDatetime
    acknowledged_at: AwareDatetime | None
    acknowledged_by: UUID | None
    resolved_at: AwareDatetime | None
    resolved_by: UUID | None
    escalation_due_at: AwareDatetime | None
    escalated_at: AwareDatetime | None
    response_started_at: AwareDatetime
    recovery_count: int
    recovery_observed_at: AwareDatetime | None
    original_assessment: Assessment | None
    latest_assessment: Assessment | None
    revision: int


class AlertEvent(BaseModel):
    id: UUID
    event_type: Literal["opened", "updated", "acknowledged", "reopened", "escalated", "resolved"]
    assessment_id: UUID | None
    caregiver_id: UUID | None
    occurred_at: AwareDatetime
    details: dict[str, str | float | None]


class AlertDetail(Alert):
    events: list[AlertEvent]


class AlertPage(BaseModel):
    items: list[Alert]
    next_cursor: str | None


class Acknowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID


class Resolve(Acknowledge):
    note: str = Field(min_length=1, max_length=500)

    @field_validator("note")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A resolution note is required.")
        return value
