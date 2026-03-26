from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models.enums import EmailDirection, EnrollmentStatus, Sentiment


class TimelineTransitionEntry(BaseModel):
    type: Literal["transition"]
    timestamp: datetime
    from_status: EnrollmentStatus | None
    to_status: EnrollmentStatus
    trigger: str


class TimelineEmailEntry(BaseModel):
    type: Literal["email"]
    timestamp: datetime
    direction: EmailDirection
    subject: str | None
    body_snippet: str
    sentiment: Sentiment | None
    step_index: int | None
    is_manual_reply: bool


TimelineEntry = Annotated[
    TimelineTransitionEntry | TimelineEmailEntry,
    Field(discriminator="type"),
]


class CandidateTimelineInfo(BaseModel):
    name: str
    email: str
    company: str | None = None
    title: str | None = None


class ReferrerInfo(BaseModel):
    referrer_name: str
    referrer_email: str


class EnrollmentTimelineResponse(BaseModel):
    candidate: CandidateTimelineInfo
    enrollment_status: EnrollmentStatus
    timeline: list[TimelineEntry]
    referral: ReferrerInfo | None = None
