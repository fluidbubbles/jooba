from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EnrollmentStatus, SequenceStatus
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.sequence_repo import SequenceRepository
from app.schemas.enrollment import CandidateInput
from app.services.exceptions import InvalidSequenceData, SequenceNotFound
from app.utils.unsubscribe import generate_unsubscribe_token

if TYPE_CHECKING:
    from app.models.sequence import Sequence


class EnrollmentService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._candidate_repo = CandidateRepository(db)
        self._enrollment_repo = EnrollmentRepository(db)
        self._sequence_repo = SequenceRepository(db)

    async def _get_sequence_or_raise(self, sequence_id: UUID) -> "Sequence":
        sequence = await self._sequence_repo.get_by_id(sequence_id)
        if sequence is None:
            raise SequenceNotFound(sequence_id)
        return sequence

    async def _require_active_sequence(self, sequence_id: UUID) -> None:
        """Raise if the sequence does not exist or is not active."""
        sequence = await self._get_sequence_or_raise(sequence_id)
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
        for candidate_input in candidates:
            normalized_email = candidate_input.email.lower().strip()
            if normalized_email in seen:
                continue

            seen.add(normalized_email)
            unique.append(candidate_input)
        return unique

    async def enroll_candidates(
        self, sequence_id: UUID, candidates: list[CandidateInput]
    ) -> dict[str, int]:
        await self._require_active_sequence(sequence_id)
        unique_candidates = self._deduplicate_candidates(candidates)

        enrolled = 0
        skipped = 0
        now = datetime.now(timezone.utc)

        for candidate_input in unique_candidates:
            candidate, _ = await self._candidate_repo.get_or_create(
                email=candidate_input.email,
                first_name=candidate_input.first_name,
                last_name=candidate_input.last_name,
                company=candidate_input.company,
                title=candidate_input.title,
            )

            token = generate_unsubscribe_token(candidate.id, sequence_id)

            # Step 0 has delay = 0, so next_send_at = now
            enrollment, is_new = await self._enrollment_repo.create_if_not_exists(
                candidate_id=candidate.id,
                sequence_id=sequence_id,
                unsubscribe_token=token,
                next_send_at=now,
            )
            if not is_new:
                skipped += 1
                continue

            await self._enrollment_repo.log_transition(
                enrollment_id=enrollment.id,
                from_status=None,
                to_status=EnrollmentStatus.ACTIVE,
                trigger="enrolled",
            )
            enrolled += 1

        return {
            "enrolled": enrolled,
            "skipped": skipped,
            "total": len(unique_candidates),
        }

    async def list_enrollments(
        self,
        sequence_id: UUID,
        status_filter: EnrollmentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Returns (items, total_count) for pagination."""
        sequence = await self._get_sequence_or_raise(sequence_id)

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
        await self._get_sequence_or_raise(sequence_id)
        return await self._enrollment_repo.get_analytics(sequence_id)
