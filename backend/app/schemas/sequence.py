import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SequenceStatus


class _OrmSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _SequenceWriteContext(BaseModel):
    role_title: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)


class StepInput(_StrictBody):
    subject: str = Field(min_length=1, max_length=500)
    body_html: str = Field(min_length=1)
    delay: int = Field(ge=0)


class StepResponse(_OrmSchema):
    id: uuid.UUID
    step_order: int
    subject: str
    body_html: str
    delay: int = Field(ge=0, validation_alias="delay_minutes")


class SequenceCreate(_StrictBody, _SequenceWriteContext):
    name: str = Field(min_length=1, max_length=255)
    steps: list[StepInput] = Field(min_length=1)


class SequenceUpdate(_StrictBody, _SequenceWriteContext):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    steps: list[StepInput] | None = None


class SequenceStatusUpdate(_StrictBody):
    status: SequenceStatus


class SequenceResponse(_OrmSchema):
    id: uuid.UUID
    name: str
    status: SequenceStatus
    role_title: str | None
    company: str | None
    created_at: datetime
    updated_at: datetime
    steps: list[StepResponse]


class SequenceListItem(_OrmSchema):
    id: uuid.UUID
    name: str
    status: SequenceStatus
    step_count: int = Field(ge=0)
    enrolled_count: int = Field(ge=0)
    replied_count: int = Field(ge=0)
    created_at: datetime


class PaginatedSequences(BaseModel):
    items: list[SequenceListItem]
    total: int
