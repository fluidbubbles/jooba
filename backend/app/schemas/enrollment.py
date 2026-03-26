from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CandidateInput(BaseModel):
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    title: str | None = None


class EnrollRequest(BaseModel):
    candidates: list[CandidateInput] = Field(..., min_length=1)


class EnrollResponse(BaseModel):
    enrolled: int
    skipped: int
    total: int


class EnrollmentListItem(BaseModel):
    id: UUID
    candidate_name: str
    candidate_email: str
    current_step: int
    total_steps: int
    status: str
    sentiment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


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
