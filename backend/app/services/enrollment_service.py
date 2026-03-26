from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.email_sender import get_email_sender
from app.models.email_event import EmailEvent
from app.models.enums import EmailDirection, EnrollmentStatus, SequenceStatus
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.nylas_account_repo import NylasAccountRepository
from app.repositories.sequence_repo import SequenceRepository
from app.schemas.enrollment import CandidateInput
from app.services.email_service import EmailService
from app.services.exceptions import InvalidSequenceData, PermanentError, SequenceNotFound
from app.utils.unsubscribe import generate_unsubscribe_token, verify_unsubscribe_token

if TYPE_CHECKING:
    from app.models.sequence import Sequence


class EnrollmentService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._candidate_repo = CandidateRepository(db)
        self._enrollment_repo = EnrollmentRepository(db)
        self._nylas_repo = NylasAccountRepository(db)
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

    async def send_email_for_enrollment(self, enrollment_id: UUID) -> None:
        """Entry point for the send task. Resolves sender + account, then delegates."""
        account = await self._nylas_repo.get_first()
        if not account:
            raise PermanentError("No email account connected")

        sender = get_email_sender()
        await self._advance_step(enrollment_id, sender=sender, grant_id=account.grant_id)

    async def _advance_step(self, enrollment_id: UUID, sender: Any, grant_id: str) -> None:
        """Send the next email for an enrollment. All business logic here."""
        enrollment = await self._enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return

        if enrollment.status != EnrollmentStatus.ACTIVE.value:
            return

        sequence = await self._sequence_repo.get_by_id(enrollment.sequence_id)
        if not sequence or not sequence.steps:
            return

        step_index = enrollment.current_step
        if step_index >= len(sequence.steps):
            return

        step = sequence.steps[step_index]

        candidate = await self._candidate_repo.get_by_id(enrollment.candidate_id)
        if not candidate:
            return

        composed = EmailService.compose(step, candidate, enrollment.unsubscribe_token)

        reply_to_id = None
        if step_index > 0:
            reply_to_id = await self._get_last_outbound_message_id(enrollment_id)

        result = sender.send(
            grant_id=grant_id,
            to=composed["to"],
            subject=composed["subject"],
            body_html=composed["body_html"],
            reply_to_message_id=reply_to_id,
        )

        event = EmailEvent(
            enrollment_id=enrollment_id,
            direction=EmailDirection.OUTBOUND.value,
            step_index=step_index,
            subject=composed["subject"],
            body_html=composed["body_html"],
            nylas_message_id=result.message_id,
            nylas_thread_id=result.thread_id,
        )
        self._db.add(event)
        await self._db.flush()

        if step_index + 1 < len(sequence.steps):
            next_step = sequence.steps[step_index + 1]
            enrollment.current_step = step_index + 1
            enrollment.next_send_at = datetime.now(timezone.utc) + timedelta(
                minutes=next_step.delay_minutes
            )
            trigger = "email_sent"
        else:
            enrollment.status = EnrollmentStatus.COMPLETED.value
            enrollment.next_send_at = None
            enrollment.completed_at = datetime.now(timezone.utc)
            trigger = "completed"

        await self._db.flush()

        await self._enrollment_repo.log_transition(
            enrollment_id=enrollment_id,
            from_status=EnrollmentStatus.ACTIVE,
            to_status=EnrollmentStatus(enrollment.status),
            trigger=trigger,
        )

    async def _get_last_outbound_message_id(self, enrollment_id: UUID) -> str | None:
        """Get the last outbound email's Nylas message ID for threading."""
        result = await self._db.execute(
            select(EmailEvent.nylas_message_id)
            .where(
                EmailEvent.enrollment_id == enrollment_id,
                EmailEvent.direction == EmailDirection.OUTBOUND.value,
            )
            .order_by(EmailEvent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_paused(self, enrollment_id: UUID) -> None:
        """Pause an enrollment (transient failures after max retries)."""
        enrollment = await self._enrollment_repo.get_by_id(enrollment_id)
        if not enrollment or enrollment.status != EnrollmentStatus.ACTIVE.value:
            return
        enrollment.status = EnrollmentStatus.PAUSED.value
        enrollment.next_send_at = None
        await self._db.flush()
        await self._enrollment_repo.log_transition(
            enrollment_id=enrollment_id,
            from_status=EnrollmentStatus.ACTIVE,
            to_status=EnrollmentStatus.PAUSED,
            trigger="max_retries_exhausted",
        )

    async def opt_out(self, token: str) -> bool:
        """Mark enrollment as opted-out via unsubscribe token.

        Returns True if the candidate is now opted out (including already-terminal
        states such as BOUNCED — the email is already undeliverable, so the intent
        is satisfied). Returns False if the token is invalid or the enrollment is
        not found.
        """
        parsed = verify_unsubscribe_token(token)
        if not parsed:
            return False

        candidate_id, sequence_id = parsed
        enrollment = await self._enrollment_repo.get_by_candidate_and_sequence(
            candidate_id, sequence_id
        )
        if not enrollment:
            return False

        # BOUNCED is treated as equivalent: email is undeliverable, so unsubscribing
        # is already satisfied — acknowledge success without re-transitioning.
        if enrollment.status in (
            EnrollmentStatus.OPTED_OUT.value,
            EnrollmentStatus.BOUNCED.value,
        ):
            return True

        old_status = enrollment.status
        enrollment.status = EnrollmentStatus.OPTED_OUT.value
        enrollment.next_send_at = None
        await self._db.flush()

        await self._enrollment_repo.log_transition(
            enrollment_id=enrollment.id,
            from_status=EnrollmentStatus(old_status),
            to_status=EnrollmentStatus.OPTED_OUT,
            trigger="unsubscribe_clicked",
        )
        return True
