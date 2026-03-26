import logging
import hmac
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.email_sender import EmailSender, get_email_sender
from app.models.email_event import EmailEvent
from app.models.enums import EmailDirection, EnrollmentStatus, SequenceStatus
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.nylas_account_repo import NylasAccountRepository
from app.repositories.sequence_repo import SequenceRepository
from app.schemas.enrollment import CandidateInput
from app.services.email_service import EmailService
from app.services.exceptions import EmailEventNotFound, InvalidSequenceData, PermanentError, SequenceNotFound
from app.utils.unsubscribe import generate_unsubscribe_token, verify_unsubscribe_token

if TYPE_CHECKING:
    from app.models.sequence import Sequence

logger = logging.getLogger(__name__)


class EnrollmentService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._candidate_repo = CandidateRepository(db)
        self._enrollment_repo = EnrollmentRepository(db)
        self._event_repo = EmailEventRepository(db)
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

    async def claim_due_enrollments_for_sending(self, limit: int = 100) -> list[UUID]:
        """Claim due enrollments for scheduler dispatch."""
        return await self._enrollment_repo.claim_due_enrollments(limit=limit)

    async def requeue_claimed_enrollment(self, enrollment_id: UUID) -> None:
        """Restore a claimed enrollment to immediate eligibility after dispatch failure."""
        await self._enrollment_repo.requeue_claimed_enrollment(enrollment_id)

    async def _pause_for_integrity(
        self,
        enrollment_id: UUID,
        trigger: str,
        message: str,
        *message_args: object,
    ) -> None:
        logger.error(message, *message_args)
        await self.mark_paused(enrollment_id, trigger=trigger)

    async def send_email_for_enrollment(self, enrollment_id: UUID) -> None:
        """Entry point for the send task. Resolves sender + account, then delegates."""
        account = await self._nylas_repo.get_first()
        if not account:
            raise PermanentError("No email account connected")

        sender = get_email_sender()
        await self._advance_step(enrollment_id, sender=sender, grant_id=account.grant_id)

    async def _advance_step(self, enrollment_id: UUID, sender: EmailSender, grant_id: str) -> None:
        """Send the current step's email, record the event, and advance to the next step or complete."""
        enrollment = await self._enrollment_repo.get_by_id_for_update(enrollment_id)
        if not enrollment:
            logger.error(
                "Enrollment %s not found during advance_step",
                enrollment_id,
            )
            return

        if enrollment.status != EnrollmentStatus.ACTIVE.value:
            logger.debug(
                "Skipping advance_step for enrollment %s - status=%s",
                enrollment_id,
                enrollment.status,
            )
            return

        if enrollment.next_send_at is not None:
            logger.debug(
                "Skipping advance_step for enrollment %s - not currently claimed",
                enrollment_id,
            )
            return

        sequence = await self._sequence_repo.get_by_id_for_update(enrollment.sequence_id)
        if not sequence or not sequence.steps:
            await self._pause_for_integrity(
                enrollment_id,
                "integrity_sequence_missing",
                "Sequence %s missing or has no steps for enrollment %s",
                enrollment.sequence_id,
                enrollment_id,
            )
            return

        if sequence.status != SequenceStatus.ACTIVE.value:
            await self._pause_for_integrity(
                enrollment_id,
                "integrity_sequence_inactive",
                "Sequence %s is %s for enrollment %s",
                enrollment.sequence_id,
                sequence.status,
                enrollment_id,
            )
            return

        step_index = enrollment.current_step
        if step_index >= len(sequence.steps):
            await self._pause_for_integrity(
                enrollment_id,
                "integrity_step_index_out_of_range",
                "Step index %d out of range for enrollment %s (sequence has %d steps)",
                step_index,
                enrollment_id,
                len(sequence.steps),
            )
            return

        step = sequence.steps[step_index]

        candidate = await self._candidate_repo.get_by_id(enrollment.candidate_id)
        if not candidate:
            await self._pause_for_integrity(
                enrollment_id,
                "integrity_candidate_missing",
                "Candidate %s not found for enrollment %s",
                enrollment.candidate_id,
                enrollment_id,
            )
            return

        composed = EmailService.compose(step, candidate, enrollment.unsubscribe_token)

        reply_to_id = (
            await self._enrollment_repo.get_latest_outbound_message_id(enrollment_id)
            if step_index > 0
            else None
        )
        idempotency_key = f"{enrollment_id}:{step_index}"

        result = sender.send(
            grant_id=grant_id,
            to=composed["to"],
            subject=composed["subject"],
            body_html=composed["body_html"],
            reply_to_message_id=reply_to_id,
            idempotency_key=idempotency_key,
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
                minutes=next_step.delay_minutes * 1440  # days → minutes
            )
            await self._enrollment_repo.log_transition(
                enrollment_id=enrollment_id,
                from_status=EnrollmentStatus.ACTIVE,
                to_status=EnrollmentStatus.ACTIVE,
                trigger="email_sent",
            )
        else:
            enrollment.current_step = step_index + 1
            enrollment.status = EnrollmentStatus.COMPLETED.value
            enrollment.next_send_at = None
            enrollment.completed_at = datetime.now(timezone.utc)
            await self._enrollment_repo.log_transition(
                enrollment_id=enrollment_id,
                from_status=EnrollmentStatus.ACTIVE,
                to_status=EnrollmentStatus.COMPLETED,
                trigger="completed",
            )

        await self._db.flush()

    async def mark_paused(
        self, enrollment_id: UUID, trigger: str = "max_retries_exhausted"
    ) -> bool:
        """Pause an enrollment (transient failures after max retries)."""
        enrollment = await self._enrollment_repo.get_by_id(enrollment_id)
        if not enrollment or enrollment.status != EnrollmentStatus.ACTIVE.value:
            return False
        enrollment.status = EnrollmentStatus.PAUSED.value
        enrollment.next_send_at = None
        await self._db.flush()
        await self._enrollment_repo.log_transition(
            enrollment_id=enrollment_id,
            from_status=EnrollmentStatus.ACTIVE,
            to_status=EnrollmentStatus.PAUSED,
            trigger=trigger,
        )
        return True

    async def mark_all_active_paused(self, trigger: str) -> int:
        """Pause all active enrollments (single-account auth failure handling)."""
        paused_count = 0
        active_ids = await self._enrollment_repo.list_active_ids()
        for active_id in active_ids:
            if await self.mark_paused(active_id, trigger=trigger):
                paused_count += 1
        return paused_count

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
        enrollment = await self._enrollment_repo.get_by_candidate_and_sequence_for_update(
            candidate_id, sequence_id
        )
        if not enrollment:
            return False

        if not enrollment.unsubscribe_token:
            return False
        if not hmac.compare_digest(enrollment.unsubscribe_token, token):
            return False

        if enrollment.status in (
            EnrollmentStatus.OPTED_OUT.value,
            EnrollmentStatus.BOUNCED.value,
            EnrollmentStatus.REPLIED.value,
            EnrollmentStatus.COMPLETED.value,
        ):
            return True

        if enrollment.status not in (
            EnrollmentStatus.ACTIVE.value,
            EnrollmentStatus.PAUSED.value,
        ):
            return False

        old_status = EnrollmentStatus(enrollment.status)
        enrollment.status = EnrollmentStatus.OPTED_OUT.value
        enrollment.next_send_at = None

        await self._enrollment_repo.log_transition(
            enrollment_id=enrollment.id,
            from_status=old_status,
            to_status=EnrollmentStatus.OPTED_OUT,
            trigger="unsubscribe_clicked",
        )
        return True

    async def mark_replied_by_event(self, email_event_id: UUID) -> None:
        """Look up event and mark its enrollment as REPLIED.

        Used by update_enrollment_on_reply task — keeps repo access in service layer.
        """
        event = await self._event_repo.find_by_id(email_event_id)
        if not event:
            raise EmailEventNotFound(email_event_id)
        await self.mark_replied(event.enrollment_id)

    async def mark_replied(self, enrollment_id: UUID) -> None:
        """Mark enrollment as REPLIED — candidate responded, cancel follow-ups."""
        enrollment = await self._enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            logger.error("mark_replied: enrollment %s not found", enrollment_id)
            return

        # Idempotency: skip if already in terminal state
        if enrollment.status in (
            EnrollmentStatus.REPLIED.value,
            EnrollmentStatus.OPTED_OUT.value,
            EnrollmentStatus.BOUNCED.value,
        ):
            logger.debug("mark_replied: enrollment %s already terminal (status=%s), skipping", enrollment_id, enrollment.status)
            return

        old_status = enrollment.status
        enrollment.status = EnrollmentStatus.REPLIED.value
        enrollment.next_send_at = None  # cancel pending follow-ups
        await self._db.flush()

        await self._enrollment_repo.log_transition(
            enrollment_id=enrollment_id,
            from_status=EnrollmentStatus(old_status),
            to_status=EnrollmentStatus.REPLIED,
            trigger="reply_received",
        )
