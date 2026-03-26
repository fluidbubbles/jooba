from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import EnrollmentStatus, Sentiment


class _OrmSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    company: str | None = Field(default=None, min_length=1, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=255)


class EnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateInput] = Field(..., min_length=1, max_length=1000)


class EnrollResponse(BaseModel):
    enrolled: int = Field(ge=0)
    skipped: int = Field(ge=0)
    total: int = Field(ge=0)


class EnrollmentListItem(_OrmSchema):
    id: UUID
    candidate_name: str
    candidate_email: str
    current_step: int
    total_steps: int
    status: EnrollmentStatus
    sentiment: Sentiment | None
    created_at: datetime


class PaginatedEnrollments(BaseModel):
    items: list[EnrollmentListItem]
    total: int


class SequenceAnalytics(BaseModel):
    enrolled: int
    sent: int
    replied: int
    interested: int
    not_interested: int
    neutral: int
    referral: int
    bounced: int
    opted_out: int
    completed: int
    paused: int
