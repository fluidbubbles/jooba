from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NylasConnectionStatus(BaseModel):
    connected: bool
    email: str | None = None
    provider: str | None = None
    connected_at: datetime | None = None


class NylasAuthUrl(BaseModel):
    url: str


class NylasDisconnectResponse(BaseModel):
    status: Literal["disconnected"] = "disconnected"
