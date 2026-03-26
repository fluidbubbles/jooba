import asyncio
import logging
from uuid import UUID

from app.celery_app import celery_app
from app.database import celery_session
from app.services.referral_service import ReferralService

logger = logging.getLogger(__name__)

REFERRAL_MAX_RETRIES = 2
REFERRAL_BACKOFF = 10


@celery_app.task(
    name="app.tasks.referral.extract_referral",
    bind=True,
    max_retries=REFERRAL_MAX_RETRIES,
    acks_late=True,
    queue="ai",
    soft_time_limit=30,
)
def extract_referral(self, email_event_id: str) -> None:
    """Extract referral contact info from a classified reply.

    Retry policy: 2 retries, fixed 10s backoff.
    """
    try:
        asyncio.run(_extract(email_event_id))
    except Exception as e:
        retries = self.request.retries
        if retries >= REFERRAL_MAX_RETRIES:
            logger.warning(
                "extract_referral exhausted retries for %s, skipping: %s",
                email_event_id,
                e,
            )
            return
        logger.warning(
            "extract_referral failed (attempt %d/%d) in %ds: %s",
            retries + 1,
            REFERRAL_MAX_RETRIES,
            REFERRAL_BACKOFF,
            e,
        )
        raise self.retry(countdown=REFERRAL_BACKOFF)


async def _extract(email_event_id: str) -> None:
    async with celery_session() as db:
        service = ReferralService(db)
        await service.process_referral(UUID(email_event_id))
        await db.commit()
