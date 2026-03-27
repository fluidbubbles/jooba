from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.referral import Referral


class ReferralRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        referrer_candidate_id: UUID,
        referred_candidate_id: UUID,
        source_email_event_id: UUID,
    ) -> Referral:
        referral = Referral(
            referrer_candidate_id=referrer_candidate_id,
            referred_candidate_id=referred_candidate_id,
            source_email_event_id=source_email_event_id,
        )
        self._db.add(referral)
        await self._db.flush()
        return referral

    async def get_by_email_event(self, email_event_id: UUID) -> Referral | None:
        result = await self._db.execute(
            select(Referral)
            .where(Referral.source_email_event_id == email_event_id)
            .order_by(Referral.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_referred_candidate(self, candidate_id: UUID) -> Referral | None:
        result = await self._db.execute(
            select(Referral)
            .where(Referral.referred_candidate_id == candidate_id)
            .order_by(Referral.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
