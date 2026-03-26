import asyncio
import logging
from uuid import UUID

from app.celery_app import celery_app
from app.database import celery_session
from app.services.classification_service import ClassificationService

logger = logging.getLogger(__name__)

CLASSIFY_MAX_RETRIES = 3
CLASSIFY_BACKOFFS = [10, 30, 90]


@celery_app.task(
    name="app.tasks.classification.classify_reply",
    bind=True,
    max_retries=3,
    acks_late=True,
    queue="ai",
    soft_time_limit=30,
)
def classify_reply(self, email_event_id: str) -> None:
    """Classify an inbound reply's sentiment via LLM.

    Retry policy: 3 retries, exponential backoff (10s, 30s, 90s).
    On exhaustion: leave sentiment null — non-critical, recruiter reads the reply.
    """
    try:
        asyncio.run(_classify(email_event_id))
    except Exception as e:
        retries = self.request.retries
        if retries >= CLASSIFY_MAX_RETRIES:
            logger.error(
                "classify_reply exhausted retries for %s, leaving sentiment null",
                email_event_id,
            )
            return
        backoff = CLASSIFY_BACKOFFS[min(retries, len(CLASSIFY_BACKOFFS) - 1)]
        logger.warning(
            "classify_reply failed (attempt %d/%d) in %ds: %s",
            retries + 1, CLASSIFY_MAX_RETRIES, backoff, e,
        )
        raise self.retry(countdown=backoff, max_retries=CLASSIFY_MAX_RETRIES)


async def _classify(email_event_id: str) -> None:
    async with celery_session() as db:
        service = ClassificationService(db)
        await service.classify(UUID(email_event_id))
        await db.commit()
