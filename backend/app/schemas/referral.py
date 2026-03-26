from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field


class ReferralInfo(BaseModel):
    name: str | None
    email: str | None
    title: str | None
    company: str | None
    referrer_name: str
    referrer_email: str
    enrolled: bool = False

    @computed_field
    @property
    def has_email(self) -> bool:
        return self.email is not None


class ReferralEnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_id: UUID
