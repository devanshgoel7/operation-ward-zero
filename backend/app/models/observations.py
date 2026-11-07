from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool

Tag = Literal["breathlessness", "dizziness", "reduced_intake"]


class ObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation_id: UUID
    tag: Tag
    present: StrictBool
    note: Annotated[str, Field(max_length=500)] | None = None


class Observation(ObservationInput):
    patient_id: UUID
    caregiver_id: UUID
    created_at: AwareDatetime
    expires_at: AwareDatetime
