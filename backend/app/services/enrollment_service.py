from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EnrollmentStatus, SequenceStatus
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.sequence_repo import SequenceRepository
from app.schemas.enrollment import CandidateInput
from app.services.exceptions import InvalidSequenceData, SequenceNotFound
from app.utils.unsubscribe import generate_unsubscribe_token


class EnrollmentService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._candidate_repo = CandidateRepository(db)
        self._enrollment_repo = EnrollmentRepository(db)
        self._sequence_repo = SequenceRepository(db)

    async def _require_active_sequence(self, sequence_id: UUID) -> None:
        """Raise if the sequence does not exist or is not active."""
        sequence = await self._sequence_repo.get_by_id(sequence_id)
        if not sequence:
            raise SequenceNotFound(sequence_id)
        if sequence.status != SequenceStatus.ACTIVE.value:
            raise InvalidSequenceData(
                f"Cannot enroll into a {sequence.status} sequence. Activate it first."
            )

    def _deduplicate_candidates(
        self, candidates: list[CandidateInput]
    ) -> list[CandidateInput]:
        """Remove batch-level email duplicates, keeping first occurrence."""
        seen: set[str] = set()
        unique: list[CandidateInput] = []
        for c in candidates:
            normalized = c.email.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                unique.append(c)
        return unique

    async def enroll_candidates(
        self, sequence_id: UUID, candidates: list[CandidateInput]
    ) -> dict[str, int]:
        await self._require_active_sequence(sequence_id)
        unique_candidates = self._deduplicate_candidates(candidates)

        enrolled = 0
        skipped = 0
        now = datetime.now(timezone.utc)

        for c in unique_candidates:
            candidate, _ = await self._candidate_repo.get_or_create(
                email=c.email,
                first_name=c.first_name,
                last_name=c.last_name,
                company=c.company,
                title=c.title,
            )

            existing = await self._enrollment_repo.get_by_candidate_and_sequence(
                candidate.id, sequence_id
            )
            if existing:
                skipped += 1
                continue

            token = generate_unsubscribe_token(candidate.id, sequence_id)

            # Step 0 has delay = 0, so next_send_at = now
            enrollment = await self._enrollment_repo.create(
                candidate_id=candidate.id,
                sequence_id=sequence_id,
                unsubscribe_token=token,
                next_send_at=now,
            )

            await self._enrollment_repo.log_transition(
                enrollment_id=enrollment.id,
                from_status=None,
                to_status=EnrollmentStatus.ACTIVE.value,
                trigger="enrolled",
            )
            enrolled += 1

        return {
            "enrolled": enrolled,
            "skipped": skipped,
            "total": len(candidates),
        }

    async def list_enrollments(
        self,
        sequence_id: UUID,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Returns (items, total_count) for pagination."""
        sequence = await self._sequence_repo.get_by_id(sequence_id)
        if not sequence:
            raise SequenceNotFound(sequence_id)

        total_steps = len(sequence.steps)
        items = await self._enrollment_repo.list_by_sequence(
            sequence_id, status_filter, limit, offset
        )
        for item in items:
            item["total_steps"] = total_steps

        total = await self._enrollment_repo.count_by_sequence(
            sequence_id, status_filter
        )
        return items, total

    async def get_analytics(self, sequence_id: UUID) -> dict[str, int]:
        sequence = await self._sequence_repo.get_by_id(sequence_id)
        if not sequence:
            raise SequenceNotFound(sequence_id)
        return await self._enrollment_repo.get_analytics(sequence_id)
