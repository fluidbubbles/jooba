import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SequenceStatus


class SequenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    status: SequenceStatus
    step_count: int = Field(ge=0)
    enrolled: int = Field(ge=0)
    sent: int = Field(ge=0)
    replied: int = Field(ge=0)
    interested: int = Field(ge=0)
    last_activity: str | None = None


class DashboardStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_candidates: int = Field(ge=0)
    total_sent: int = Field(ge=0)
    total_replies: int = Field(ge=0)
    reply_rate: float = Field(ge=0)
    total_interested: int = Field(ge=0)
    unreplied_count: int = Field(ge=0)
    sequences: list[SequenceSummary]
