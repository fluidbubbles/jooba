import asyncio
import logging

from app.celery_app import celery_app
from app.database import async_session
from app.repositories.enrollment_repo import EnrollmentRepository
from app.tasks.dispatcher import get_dispatcher

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.scheduler.send_due_emails")
def send_due_emails() -> None:
    """Periodic task: claim due enrollments and dispatch individual send tasks."""
    asyncio.run(_claim_and_dispatch())


async def _claim_and_dispatch() -> None:
    async with async_session() as db:
        repo = EnrollmentRepository(db)
        claimed_ids = await repo.claim_due_enrollments(limit=100)
        await db.commit()

    logger.debug("Scheduler claimed %d enrollment(s) for sending", len(claimed_ids))
    dispatcher = get_dispatcher()
    for enrollment_id in claimed_ids:
        try:
            dispatcher.dispatch(
                "app.tasks.email_sending.send_sequence_email",
                str(enrollment_id),
                queue="email",
            )
        except Exception:
            logger.exception(
                "Failed to dispatch send task for enrollment %s", enrollment_id
            )
