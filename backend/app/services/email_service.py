import asyncio
import logging
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.email_sender import get_email_sender
from app.integrations.nylas_client import NylasClient
from app.models.candidate import Candidate
from app.models.enums import EmailDirection, EnrollmentStatus
from app.models.enrollment import Enrollment
from app.models.sequence import SequenceStep
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.nylas_account_repo import NylasAccountRepository
from app.services.exceptions import DomainError, EmailEventNotFound, PermanentError
from app.tasks.dispatcher import TaskDispatcher, get_dispatcher
from app.utils.templates import append_unsubscribe_footer, replace_placeholders

logger = logging.getLogger(__name__)
REPLY_SUBJECT_PREFIX_RE = re.compile(r"^(?:\s*re\s*:\s*)+", re.IGNORECASE)


def build_reply_subject(subject: str | None) -> str:
    """Normalize subject so manual replies always have a single Re: prefix."""
    normalized = REPLY_SUBJECT_PREFIX_RE.sub("", (subject or "").strip()).strip()
    return f"Re: {normalized}" if normalized else "Re:"


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

        # Webhook deduplication: skip if message already recorded
        if message_id:
            existing = await self._event_repo.find_by_message_id(message_id)
            if existing:
                logger.info("Webhook dedup: message %s already recorded, skipping", message_id)
                return

        # Match to enrollment
        enrollment, matched_by_thread = await self._match_to_enrollment(thread_id, sender_email)
        if not enrollment:
            logger.info(
                "Webhook: no enrollment match for thread=%s sender=%s — discarding",
                thread_id, sender_email,
            )
            return
        logger.info(
            "Webhook: matched enrollment %s (by_thread=%s)", enrollment.id, matched_by_thread
        )

        # Determine direction
        account = await self._nylas_repo.get_first()
        if not account:
            logger.warning("Webhook: no Nylas account configured, cannot determine direction")
            return
        account_email = account.email.lower()

        if sender_email == account_email:
            # Only record external recruiter replies when matched by thread (recruiter replied on an
            # existing thread).  When matched via sender-email fallback, this is Nylas re-indexing
            # Jooba's own sent email under a new thread ID — skip it to avoid duplicate timeline entries.
            if matched_by_thread:
                await self._record_external_reply(
                    enrollment,
                    subject=subject,
                    body_html=body_html,
                    body_text=body_text,
                    message_id=message_id,
                    thread_id=thread_id,
                )
            else:
                logger.info(
                    "Webhook: outbound matched via sender-email fallback (Nylas re-index), "
                    "skipping. thread=%s", thread_id,
                )
            return

        # Inbound dedup at enrollment level: the same reply can arrive with different Nylas
        # message IDs when Gmail re-threads.  If this enrollment already has a recent inbound
        # from this sender, treat it as a duplicate and skip.
        recent_inbound = await self._event_repo.find_recent_inbound(
            enrollment.id, sender_email, within_seconds=120
        )
        if recent_inbound:
            logger.info(
                "Webhook inbound dedup: enrollment %s already has recent inbound from %s, skipping",
                enrollment.id, sender_email,
            )
            return

        logger.info(
            "Webhook: recording inbound from %s on enrollment %s (message_id=%s)",
            sender_email, enrollment.id, message_id,
        )
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

    async def _match_to_enrollment(
        self, thread_id: str | None, sender_email: str
    ) -> tuple["Enrollment | None", bool]:
        """Match an incoming message to an enrollment.

        Returns (enrollment, matched_by_thread).  matched_by_thread is True when
        the match came from an existing thread_id, False when it came from the
        sender-email fallback.  Callers use this to distinguish a recruiter
        replying on an existing thread (matched_by_thread=True) from Nylas
        re-indexing Jooba's own sent email under a new thread (matched_by_thread=False).

        When thread_id is present but not found, refuses sender-email fallback to avoid
        mis-attaching old replies to a different enrollment for the same candidate.
        """
        if thread_id:
            event = await self._event_repo.find_by_thread_id(thread_id)
            if event:
                enrollment = await self._enrollment_repo.get_by_id(event.enrollment_id)
                if enrollment:
                    return enrollment, True
            return None, False

        if sender_email:
            candidate = await self._candidate_repo.get_by_email(sender_email)
            if candidate:
                enrollment = await self._enrollment_repo.get_latest_by_candidate(
                    candidate.id,
                    [EnrollmentStatus.ACTIVE, EnrollmentStatus.REPLIED],
                )
                if enrollment:
                    return enrollment, False

        return None, False

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
            raise EmailEventNotFound(email_event_id)

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

        reply_subject = build_reply_subject(original.subject)

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

    async def poll_new_messages(self, received_after: int, nylas_client: NylasClient | None = None) -> int:
        """Poll Nylas for new messages and process each through process_webhook.

        Returns the max message timestamp for watermark advancement.
        Only advances past messages that were successfully processed.
        """
        account = await self._nylas_repo.get_first()
        if not account:
            return received_after

        client = nylas_client or NylasClient()
        account_email = account.email.lower()

        messages = await asyncio.to_thread(
            client.list_messages, account.grant_id, received_after,
        )
        if not messages:
            return received_after

        logger.info("Poller found %d message(s) since ts=%d", len(messages), received_after)

        max_processed_ts = received_after
        for msg in messages:
            if msg["sender_email"].lower() == account_email:
                continue

            logger.info(
                "Poller processing: id=%s from=%s subj=%s",
                msg["message_id"], msg["sender_email"], (msg["subject"] or "")[:40],
            )
            try:
                await self.process_webhook(msg)
                await self._db.commit()
                if msg["date"] > max_processed_ts:
                    max_processed_ts = msg["date"]
            except Exception:
                logger.exception("Poller: failed processing message %s", msg["message_id"])
                await self._db.rollback()

        return max_processed_ts
