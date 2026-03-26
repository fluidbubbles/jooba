from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate


class CandidateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_email(self, email: str) -> Candidate | None:
        result = await self._db.execute(
            select(Candidate).where(Candidate.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, candidate_id: UUID) -> Candidate | None:
        result = await self._db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        first_name: str | None = None,
        last_name: str | None = None,
        company: str | None = None,
        title: str | None = None,
    ) -> Candidate:
        candidate = Candidate(
            email=email.lower().strip(),
            first_name=first_name,
            last_name=last_name,
            company=company,
            title=title,
        )
        self._db.add(candidate)
        await self._db.flush()
        return candidate

    async def get_or_create(
        self, email: str, **kwargs: str | None
    ) -> tuple[Candidate, bool]:
        """Returns (candidate, is_new)."""
        existing = await self.get_by_email(email)
        if existing:
            return existing, False
        created = await self.create(email=email, **kwargs)
        return created, True
