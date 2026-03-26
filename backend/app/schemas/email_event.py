from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InboxReplyItem(BaseModel):
    id: str
    enrollment_id: str
    candidate_name: str
    candidate_email: str
    body_snippet: str
    sentiment: str | None
    sentiment_reasoning: str | None
    sequence_name: str
    created_at: datetime
    is_unreplied: bool = False


class ThreadEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    direction: str
    subject: str | None
    body_html: str | None
    body_text: str | None
    sentiment: str | None
    sentiment_reasoning: str | None
    is_manual_reply: bool
    step_index: int | None
    created_at: datetime


class ReplyDetail(BaseModel):
    enrollment_id: str
    candidate_name: str
    candidate_email: str
    sequence_name: str
    sentiment: str | None
    sentiment_reasoning: str | None
    thread: list[ThreadEvent]


class ManualReplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_html: str


class SentimentCounts(BaseModel):
    all: int = 0
    interested: int = 0
    not_interested: int = 0
    referral: int = 0
    neutral: int = 0
