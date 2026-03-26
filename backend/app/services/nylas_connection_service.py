import asyncio
import hashlib
import hmac
import secrets
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.nylas_client import NylasClient
from app.repositories.nylas_account_repo import NylasAccountRepository
from app.schemas.nylas import NylasConnectionStatus

_OAUTH_STATE_TTL_SECONDS = 600


class NylasConnectionService:
    def __init__(self, db: AsyncSession, client: NylasClient | None = None) -> None:
        self._db = db
        self._client = client or NylasClient()
        self._repo = NylasAccountRepository(db)

    def get_auth_url(self) -> str:
        state = self.generate_oauth_state()
        return self._client.get_auth_url(state=state)

    async def complete_oauth_callback(self, code: str) -> None:
        grant_data = await asyncio.to_thread(self._client.exchange_code_for_grant, code)
        await self._repo.replace_single_account(
            grant_id=grant_data["grant_id"],
            email=grant_data["email"],
            provider=grant_data.get("provider", "unknown"),
        )

    async def get_connection_status(self) -> NylasConnectionStatus:
        account = await self._repo.get_first()
        if not account:
            return NylasConnectionStatus(connected=False)
        return NylasConnectionStatus(
            connected=True,
            email=account.email,
            provider=account.provider,
            connected_at=account.connected_at,
        )

    async def disconnect(self) -> None:
        await self._repo.delete_all()

    def generate_oauth_state(self) -> str:
        issued_at = str(int(time.time()))
        nonce = secrets.token_urlsafe(18)
        payload = f"{issued_at}:{nonce}"
        signature = self._sign_state_payload(payload)
        return f"{payload}:{signature}"

    def validate_oauth_state(self, state: str | None) -> bool:
        if not state:
            return False
        parts = state.split(":")
        if len(parts) != 3:
            return False

        issued_at_raw, nonce, received_signature = parts
        if not nonce:
            return False

        try:
            issued_at = int(issued_at_raw)
        except ValueError:
            return False

        now = int(time.time())
        if issued_at > now + 60:
            return False
        if now - issued_at > _OAUTH_STATE_TTL_SECONDS:
            return False

        payload = f"{issued_at_raw}:{nonce}"
        expected_signature = self._sign_state_payload(payload)
        return hmac.compare_digest(expected_signature, received_signature)

    def _sign_state_payload(self, payload: str) -> str:
        return hmac.new(
            settings.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
