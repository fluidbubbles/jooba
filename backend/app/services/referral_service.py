import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.openai_client import OpenAIClient
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.referral_repo import ReferralRepository
from app.utils.name_parse import format_display_name, split_full_name

logger = logging.getLogger(__name__)

_PLACEHOLDER_EMAIL_SUFFIX = "@placeholder.local"


class ReferralService:
    def __init__(self, db: AsyncSession) -> None:
        self._event_repo = EmailEventRepository(db)
        self._candidate_repo = CandidateRepository(db)
        self._referral_repo = ReferralRepository(db)
        self._enrollment_repo = EnrollmentRepository(db)
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

        return {
            "name": format_display_name(referred.first_name, referred.last_name),
            "email": None if is_placeholder else referred.email,
            "title": referred.title,
            "company": referred.company,
            "referrer_name": format_display_name(referrer.first_name, referrer.last_name)
            or "",
            "referrer_email": referrer.email,
            "has_email": not is_placeholder,
        }
