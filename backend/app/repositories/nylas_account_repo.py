from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nylas_account import NylasAccount


class NylasAccountRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_first(self) -> NylasAccount | None:
        """Get the connected account (single-user app)."""
        result = await self._db.execute(select(NylasAccount).limit(1))
        return result.scalar_one_or_none()

    async def replace_single_account(
        self,
        grant_id: str,
        email: str,
        provider: str = "unknown",
    ) -> NylasAccount:
        """Replace the single connected account."""
        await self._db.execute(delete(NylasAccount))
        account = NylasAccount(grant_id=grant_id, email=email, provider=provider)
        self._db.add(account)
        await self._db.flush()
        return account

    async def delete_all(self) -> None:
        """Disconnect — remove all accounts (single-user, so just one)."""
        await self._db.execute(delete(NylasAccount))
        await self._db.flush()
