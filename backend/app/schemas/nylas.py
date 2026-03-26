from datetime import datetime

from pydantic import BaseModel


class NylasConnectionStatus(BaseModel):
    connected: bool
    email: str | None = None
    provider: str | None = None
    connected_at: datetime | None = None


class NylasAuthUrl(BaseModel):
    url: str
