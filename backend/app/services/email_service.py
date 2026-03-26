import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.email_sender import get_email_sender
from app.models.candidate import Candidate
from app.models.enums import EmailDirection, EnrollmentStatus
from app.models.enrollment import Enrollment
from app.models.sequence import SequenceStep
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.nylas_account_repo import NylasAccountRepository
from app.services.exceptions import DomainError, PermanentError
from app.tasks.dispatcher import TaskDispatcher, get_dispatcher
from app.utils.templates import append_unsubscribe_footer, replace_placeholders

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self, db: AsyncSession, dispatcher: TaskDispatcher | None = None) -> None:
        self._db = db
        self._event_repo = EmailEventRepository(db)
        self._enrollment_repo = EnrollmentRepository(db)
        self._candidate_repo = CandidateRepository(db)
        self._nylas_repo = NylasAccountRepository(db)
        self._dispatcher = dispatcher or get_dispatcher()

    @staticmethod
    def compose(step: SequenceStep, candidate: Candidate, unsubscribe_token: str) -> dict:
        """Compose an email from a sequence step + candidate data."""
        candidate_data = {
            "first_name": candidate.first_name or "",
            "last_name": candidate.last_name or "",
            "company": candidate.company or "",
            "title": candidate.title or "",
            "email": candidate.email,
        }
        subject = replace_placeholders(step.subject, candidate_data)
        body = replace_placeholders(step.body_html, candidate_data)
        unsubscribe_url = f"{settings.unsubscribe_base_url}/{unsubscribe_token}"
        body = append_unsubscribe_footer(body, unsubscribe_url)
        return {"to": candidate.email, "subject": subject, "body_html": body}

    async def process_webhook(self, data: dict) -> None:
        """Process a Nylas webhook notification for a new message."""
        message_id = data.get("message_id")
        thread_id = data.get("thread_id")
        sender_email = data.get("sender_email", "").lower()
        subject = data.get("subject", "")
        body_html = data.get("body_html", "")
        body_text = data.get("body_text", "")

        # Webhook deduplication (unique constraint on nylas_message_id)
        if message_id:
            existing = await self._event_repo.find_by_message_id(message_id)
            if existing:
                logger.debug("Webhook dedup: message %s already processed", message_id)
                return

        # Match to enrollment
        enrollment = await self._match_to_enrollment(thread_id, sender_email)
        if not enrollment:
            logger.debug("Webhook: no enrollment match for thread=%s sender=%s", thread_id, sender_email)
            return

        # Determine direction
        account = await self._nylas_repo.get_first()
        if not account:
            logger.warning("Webhook: no Nylas account configured, cannot determine direction")
            return
        account_email = account.email.lower()

        if sender_email == account_email:
            await self._record_external_reply(
                enrollment,
                subject=subject,
                body_html=body_html,
                body_text=body_text,
                message_id=message_id,
                thread_id=thread_id,
            )
            return

        # Inbound — candidate reply
        event = await self._event_repo.create(
            enrollment_id=enrollment.id,
            direction=EmailDirection.INBOUND,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            nylas_message_id=message_id,
            nylas_thread_id=thread_id,
        )

        # Dispatch parallel tasks
        self._dispatcher.dispatch(
            "app.tasks.classification.classify_reply",
            str(event.id),
            queue="ai",
        )
        self._dispatcher.dispatch(
            "app.tasks.enrollment.update_enrollment_on_reply",
            str(event.id),
            queue="default",
        )

    async def _match_to_enrollment(self, thread_id: str | None, sender_email: str) -> Enrollment | None:
        """Match an incoming message to an enrollment.

        Try 1: thread_id match (most reliable — same email thread)
        Try 2: sender email match to candidate with active/replied enrollment (fallback)
        """
        if thread_id:
            event = await self._event_repo.find_by_thread_id(thread_id)
            if event:
                return await self._enrollment_repo.get_by_id(event.enrollment_id)

        if sender_email:
            candidate = await self._candidate_repo.get_by_email(sender_email)
            if candidate:
                return await self._enrollment_repo.get_latest_by_candidate(
                    candidate.id,
                    [EnrollmentStatus.ACTIVE, EnrollmentStatus.REPLIED],
                )

        return None

    async def _record_external_reply(
        self,
        enrollment: Enrollment,
        *,
        subject: str,
        body_html: str,
        body_text: str,
        message_id: str | None,
        thread_id: str | None,
    ) -> None:
        """Record an outbound reply the recruiter sent from their email client."""
        await self._event_repo.create(
            enrollment_id=enrollment.id,
            direction=EmailDirection.OUTBOUND,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            nylas_message_id=message_id,
            nylas_thread_id=thread_id,
            is_manual_reply=False,
        )

    async def send_manual_reply(self, email_event_id: UUID, body_html: str) -> dict:
        """Send a reply from the inbox and record it. Per Architecture Section 5.6."""
        original = await self._event_repo.find_by_id(email_event_id)
        if not original:
            raise DomainError("Email event not found", "EMAIL_EVENT_NOT_FOUND")

        enrollment = await self._enrollment_repo.get_by_id(original.enrollment_id)
        if not enrollment:
            raise DomainError("Enrollment not found", "ENROLLMENT_NOT_FOUND")

        candidate = await self._candidate_repo.get_by_id(enrollment.candidate_id)
        if not candidate:
            raise DomainError("Candidate not found", "CANDIDATE_NOT_FOUND")

        # Append unsubscribe footer
        unsub_url = f"{settings.unsubscribe_base_url}/{enrollment.unsubscribe_token}"
        body_with_footer = append_unsubscribe_footer(body_html, unsub_url)

        # Send via provider
        account = await self._nylas_repo.get_first()
        if not account:
            raise PermanentError("No email account connected")

        reply_subject = f"Re: {original.subject or ''}"

        sender = get_email_sender()
        result = sender.send(
            grant_id=account.grant_id,
            to=candidate.email,
            subject=reply_subject,
            body_html=body_with_footer,
            reply_to_message_id=original.nylas_message_id,
        )

        # Record the outbound event
        event = await self._event_repo.create(
            enrollment_id=enrollment.id,
            direction=EmailDirection.OUTBOUND,
            subject=reply_subject,
            body_html=body_with_footer,
            nylas_message_id=result.message_id,
            nylas_thread_id=result.thread_id,
            is_manual_reply=True,
        )

        # Log transition (status stays same, just recording the manual reply action)
        await self._enrollment_repo.log_transition(
            enrollment_id=enrollment.id,
            from_status=EnrollmentStatus(enrollment.status),
            to_status=EnrollmentStatus(enrollment.status),
            trigger="manual_reply_sent",
        )

        return {"message_id": result.message_id, "event_id": str(event.id)}
