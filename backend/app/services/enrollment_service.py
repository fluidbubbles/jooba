from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SequenceStatus
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

    async def enroll_candidates(
        self, sequence_id: UUID, candidates: list[CandidateInput]
    ) -> dict:
        # Validate sequence exists and is active
        sequence = await self._sequence_repo.get_by_id(sequence_id)
        if not sequence:
            raise SequenceNotFound(str(sequence_id))
        if sequence.status != SequenceStatus.ACTIVE.value:
            raise InvalidSequenceData(
                f"Cannot enroll into a {sequence.status} sequence. Activate it first."
            )

        # Deduplicate by email within the batch
        seen_emails: set[str] = set()
        unique_candidates: list[CandidateInput] = []
        for c in candidates:
            email_lower = c.email.lower().strip()
            if email_lower not in seen_emails:
                seen_emails.add(email_lower)
                unique_candidates.append(c)

        enrolled = 0
        skipped = 0
        now = datetime.now(timezone.utc)

        for c in unique_candidates:
            # Get or create candidate
            candidate, _is_new = await self._candidate_repo.get_or_create(
                email=c.email,
                first_name=c.first_name,
                last_name=c.last_name,
                company=c.company,
                title=c.title,
            )

            # Check if already enrolled in this sequence
            existing = await self._enrollment_repo.get_by_candidate_and_sequence(
                candidate.id, sequence_id
            )
            if existing:
                skipped += 1
                continue

            # Generate unsubscribe token
            token = generate_unsubscribe_token(candidate.id, sequence_id)

            # Create enrollment — step 0 delay = 0, so next_send_at = now
            enrollment = await self._enrollment_repo.create(
                candidate_id=candidate.id,
                sequence_id=sequence_id,
                unsubscribe_token=token,
                next_send_at=now,
            )

            # Log state transition
            await self._enrollment_repo.log_transition(
                enrollment_id=enrollment.id,
                from_status=None,
                to_status="active",
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
    ) -> tuple[list[dict], int]:
        """Returns (items, total_count) for pagination."""
        # Verify sequence exists
        sequence = await self._sequence_repo.get_by_id(sequence_id)
        if not sequence:
            raise SequenceNotFound(str(sequence_id))

        total_steps = len(sequence.steps)
        items = await self._enrollment_repo.list_by_sequence(
            sequence_id, status_filter, limit, offset
        )
        # Attach total_steps to each item
        for item in items:
            item["total_steps"] = total_steps

        total = await self._enrollment_repo.count_by_sequence(
            sequence_id, status_filter
        )
        return items, total

    async def get_analytics(self, sequence_id: UUID) -> dict:
        sequence = await self._sequence_repo.get_by_id(sequence_id)
        if not sequence:
            raise SequenceNotFound(str(sequence_id))
        return await self._enrollment_repo.get_analytics(sequence_id)
