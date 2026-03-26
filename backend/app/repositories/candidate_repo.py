from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate


class CandidateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    async def get_by_email(self, email: str) -> Candidate | None:
        normalized_email = self._normalize_email(email)
        result = await self._db.execute(
            select(Candidate).where(Candidate.email == normalized_email)
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
        normalized_email = self._normalize_email(email)
        candidate = Candidate(
            email=normalized_email,
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
        if existing is not None:
            return existing, False

        try:
            async with self._db.begin_nested():
                created = await self.create(email=email, **kwargs)
            return created, True
        except IntegrityError:
            # Another concurrent transaction may have inserted the same normalized
            # email between our lookup and insert.
            existing = await self.get_by_email(email)
            if existing is not None:
                return existing, False
            raise
