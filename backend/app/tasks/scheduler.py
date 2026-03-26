import asyncio
import logging

from app.celery_app import celery_app
from app.database import celery_session
from app.repositories.enrollment_repo import EnrollmentRepository

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.scheduler.send_due_emails")
def send_due_emails() -> None:
    """Periodic task: claim due enrollments and dispatch individual send tasks."""
    asyncio.run(_claim_and_dispatch())


async def _claim_and_dispatch() -> None:
    async with celery_session() as db:
        repo = EnrollmentRepository(db)
        claimed_ids = await repo.claim_due_enrollments(limit=100)
        await db.commit()

    if claimed_ids:
        logger.info("Scheduler claimed %d enrollment(s) for sending", len(claimed_ids))
    for enrollment_id in claimed_ids:
        try:
            # Scheduler runs inside Celery — dispatch child tasks directly.
            # The TaskDispatcher abstraction is for services running outside Celery.
            celery_app.send_task(
                "app.tasks.email_sending.send_sequence_email",
                args=[str(enrollment_id)],
                queue="email",
            )
        except Exception:
            logger.exception(
                "Failed to dispatch send task for enrollment %s", enrollment_id
            )
