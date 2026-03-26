import asyncio
import logging
from uuid import UUID

from app.celery_app import celery_app
from app.database import celery_session
from app.services.enrollment_service import EnrollmentService

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.enrollment.update_enrollment_on_reply",
    bind=True,
    max_retries=3,
    acks_late=True,
    queue="default",
)
def update_enrollment_on_reply(self, email_event_id: str) -> None:
    """Mark enrollment as REPLIED when candidate replies.

    Retry policy: 3 retries, immediate retry.
    Critical — must not lose reply state.
    """
    try:
        asyncio.run(_update(email_event_id))
    except Exception as e:
        retries = self.request.retries
        if retries >= 3:
            logger.critical(
                "update_enrollment_on_reply exhausted retries for %s — reply state may be lost",
                email_event_id,
            )
            return
        logger.error(
            "update_enrollment_on_reply failed (attempt %d/3): %s",
            retries + 1, e,
        )
        raise self.retry(countdown=0, max_retries=3)


async def _update(email_event_id: str) -> None:
    async with celery_session() as db:
        service = EnrollmentService(db)
        await service.mark_replied_by_event(UUID(email_event_id))
        await db.commit()
