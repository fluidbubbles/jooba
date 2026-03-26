import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.openai_client import OpenAIClient
from app.models.enums import EnrollmentStatus, SequenceStatus
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.referral_repo import ReferralRepository
from app.repositories.sequence_repo import SequenceRepository
from app.utils.name_parse import format_display_name, split_full_name
from app.utils.unsubscribe import generate_unsubscribe_token

logger = logging.getLogger(__name__)

_PLACEHOLDER_EMAIL_SUFFIX = "@placeholder.local"


class ReferralService:
    def __init__(self, db: AsyncSession) -> None:
        self._event_repo = EmailEventRepository(db)
        self._candidate_repo = CandidateRepository(db)
        self._referral_repo = ReferralRepository(db)
        self._enrollment_repo = EnrollmentRepository(db)
        self._sequence_repo = SequenceRepository(db)
        self._openai = OpenAIClient()

    async def process_referral(self, email_event_id: UUID) -> None:
        """Extract referral info from a classified reply and create records (idempotent)."""
        event = await self._event_repo.find_by_id_for_update(email_event_id)
        if not event:
            logger.warning("process_referral called for missing event %s", email_event_id)
            return

        existing = await self._referral_repo.get_by_email_event(email_event_id)
        if existing is not None:
            logger.debug("referral already exists for event %s, skipping", email_event_id)
            return

        enrollment = await self._enrollment_repo.get_by_id(event.enrollment_id)
        if enrollment is None:
            logger.error(
                "process_referral: enrollment %s missing for event %s",
                event.enrollment_id,
                email_event_id,
            )
            return

        referrer = await self._candidate_repo.get_by_id(enrollment.candidate_id)
        if referrer is None:
            logger.error(
                "process_referral: referrer candidate %s missing for event %s",
                enrollment.candidate_id,
                email_event_id,
            )
            return

        reply_text = event.body_html or event.body_text or ""
        extraction = self._openai.extract_referral(reply_text)

        if not extraction.name and not extraction.email:
            logger.debug(
                "referral extraction for event %s produced no name or email, skipping",
                email_event_id,
            )
            return

        first_name, last_name = split_full_name(extraction.name)

        candidate_email = (
            extraction.email
            if extraction.email
            else f"referral-{email_event_id}{_PLACEHOLDER_EMAIL_SUFFIX}"
        )
        referred, _ = await self._candidate_repo.get_or_create(
            email=candidate_email,
            first_name=first_name,
            last_name=last_name,
            company=extraction.company,
            title=extraction.title,
        )

        await self._referral_repo.create(
            referrer_candidate_id=referrer.id,
            referred_candidate_id=referred.id,
            source_email_event_id=email_event_id,
        )

        # Auto-enroll based on whether we have the referred person's email
        if candidate_email.endswith(_PLACEHOLDER_EMAIL_SUFFIX):
            # Missing email — ask the referrer for clarification
            await self._auto_enroll_into(
                candidate_id=referrer.id,
                sequence_name=settings.referral_clarification_sequence_name,
                trigger="referral_clarification",
            )
        else:
            # Have email — reach out to the referred person
            await self._auto_enroll_into(
                candidate_id=referred.id,
                sequence_name=settings.referral_sequence_name,
                trigger="referral_auto_enrolled",
            )
            # Thank the referrer
            await self._auto_enroll_into(
                candidate_id=referrer.id,
                sequence_name=settings.referral_thank_you_sequence_name,
                trigger="referral_thank_you",
            )

    async def _auto_enroll_into(
        self, candidate_id: UUID, sequence_name: str, trigger: str,
    ) -> None:
        """Enroll a candidate into the named sequence if it exists and is active."""
        sequence = await self._sequence_repo.get_by_name(sequence_name)
        if not sequence:
            logger.warning(
                "Sequence '%s' not found, skipping auto-enrollment", sequence_name,
            )
            return
        if sequence.status != SequenceStatus.ACTIVE.value:
            logger.warning(
                "Sequence '%s' is %s, skipping auto-enrollment",
                sequence_name, sequence.status,
            )
            return

        token = generate_unsubscribe_token(candidate_id, sequence.id)
        enrollment, is_new = await self._enrollment_repo.create_if_not_exists(
            candidate_id=candidate_id,
            sequence_id=sequence.id,
            unsubscribe_token=token,
            next_send_at=datetime.now(timezone.utc),
        )
        if is_new:
            await self._enrollment_repo.log_transition(
                enrollment_id=enrollment.id,
                from_status=None,
                to_status=EnrollmentStatus.ACTIVE,
                trigger=trigger,
            )
            logger.info(
                "Auto-enrolled candidate %s into '%s' (trigger=%s)",
                candidate_id, sequence_name, trigger,
            )

    async def get_referral_for_event(self, email_event_id: UUID) -> dict | None:
        referral = await self._referral_repo.get_by_email_event(email_event_id)
        if referral is None:
            return None

        referrer = await self._candidate_repo.get_by_id(referral.referrer_candidate_id)
        referred = await self._candidate_repo.get_by_id(referral.referred_candidate_id)
        if referrer is None or referred is None:
            logger.error(
                "get_referral_for_event: missing candidate row(s) for referral %s",
                referral.id,
            )
            return None

        is_placeholder = referred.email.endswith(_PLACEHOLDER_EMAIL_SUFFIX)

        # Check if already auto-enrolled into referral sequence
        enrolled = False
        sequence = await self._sequence_repo.get_by_name(settings.referral_sequence_name)
        if sequence:
            existing = await self._enrollment_repo.get_by_candidate_and_sequence(
                referred.id, sequence.id,
            )
            enrolled = existing is not None

        return {
            "name": format_display_name(referred.first_name, referred.last_name),
            "email": None if is_placeholder else referred.email,
            "title": referred.title,
            "company": referred.company,
            "referrer_name": format_display_name(referrer.first_name, referrer.last_name)
            or "",
            "referrer_email": referrer.email,
            "enrolled": enrolled,
        }
