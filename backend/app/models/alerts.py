from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

Priority = Literal["watch", "high"]
Status = Literal["open", "acknowledged"]


class Finding(BaseModel):
    rule_id: str
    priority: Priority
    metric: str
    value: float
    unit: str
    condition: str
    reading_id: UUID
    observed_at: AwareDatetime


class Assessment(BaseModel):
    id: UUID
    patient_id: UUID
    reading_id: UUID
    scope: Literal["current", "historical"]
    concern: Literal["none", "watch", "high"] | None
    data_quality: Literal["fresh", "incomplete"]
    evaluated_at: AwareDatetime
    rule_version: str
    findings: list[Finding]


class Alert(BaseModel):
    id: UUID
    patient_id: UUID
    kind: Literal["risk"]
    status: Status
    peak_priority: Priority
    assignee_id: UUID
    opened_at: AwareDatetime
    acknowledged_at: AwareDatetime | None
    acknowledged_by: UUID | None
    original_assessment: Assessment
    latest_assessment: Assessment
    revision: int


class AlertEvent(BaseModel):
    id: UUID
    event_type: Literal["opened", "updated", "acknowledged", "reopened", "escalated"]
    assessment_id: UUID | None
    caregiver_id: UUID | None
    occurred_at: AwareDatetime


class AlertDetail(Alert):
    events: list[AlertEvent]


class AlertPage(BaseModel):
    items: list[Alert]
    next_cursor: str | None


class Acknowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
