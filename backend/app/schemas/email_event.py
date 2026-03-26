from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmailDirection, Sentiment


class InboxReplyItem(BaseModel):
    id: str
    enrollment_id: str
    candidate_name: str
    candidate_email: str
    body_snippet: str
    sentiment: Sentiment | None
    sentiment_reasoning: str | None
    sequence_name: str
    created_at: datetime
    is_unreplied: bool = False


class ThreadEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    direction: EmailDirection
    subject: str | None
    body_html: str | None
    body_text: str | None
    sentiment: Sentiment | None
    sentiment_reasoning: str | None
    is_manual_reply: bool
    step_index: int | None
    created_at: datetime


class ReplyDetail(BaseModel):
    enrollment_id: str
    candidate_name: str
    candidate_email: str
    sequence_name: str
    current_step: int
    total_steps: int
    sentiment: Sentiment | None
    sentiment_reasoning: str | None
    thread: list[ThreadEvent]


class ManualReplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_html: str = Field(min_length=1)


class SentimentCounts(BaseModel):
    all: int = Field(default=0, ge=0)
    interested: int = Field(default=0, ge=0)
    not_interested: int = Field(default=0, ge=0)
    referral: int = Field(default=0, ge=0)
    neutral: int = Field(default=0, ge=0)
