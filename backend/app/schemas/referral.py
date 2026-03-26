from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReferralInfo(BaseModel):
    name: str | None
    email: str | None
    title: str | None
    company: str | None
    referrer_name: str
    referrer_email: str
    has_email: bool


class ReferralEnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_id: UUID
