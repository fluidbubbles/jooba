from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import EnrollmentStatus, Sentiment


class _OrmSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CandidateInput(BaseModel):
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    title: str | None = None


class EnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateInput] = Field(..., min_length=1)


class EnrollResponse(BaseModel):
    enrolled: int
    skipped: int
    total: int


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
