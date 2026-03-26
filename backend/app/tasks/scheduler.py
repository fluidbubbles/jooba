import asyncio
import logging
from uuid import UUID

from app.celery_app import celery_app
from app.database import celery_session
from app.services.enrollment_service import EnrollmentService
from app.tasks.dispatcher import TaskDispatcher, get_dispatcher

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.scheduler.send_due_emails")
def send_due_emails() -> None:
    """Periodic task: claim due enrollments and dispatch individual send tasks."""
    asyncio.run(_claim_and_dispatch())


async def _claim_and_dispatch() -> None:
    async with celery_session() as db:
        service = EnrollmentService(db)
        claimed_ids = await service.claim_due_enrollments_for_sending(limit=100)
        await db.commit()

    if not claimed_ids:
        return

    dispatcher = get_dispatcher()
    logger.info("Scheduler claimed %d enrollment(s) for sending", len(claimed_ids))
    for enrollment_id in claimed_ids:
        await _dispatch_send_or_requeue(dispatcher, enrollment_id)


async def _dispatch_send_or_requeue(
    dispatcher: TaskDispatcher, enrollment_id: UUID
) -> None:
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
        try:
            await _requeue_claimed_enrollment(enrollment_id)
        except Exception:
            logger.exception(
                "Failed to requeue claimed enrollment %s after dispatch failure",
                enrollment_id,
            )
            raise


async def _requeue_claimed_enrollment(enrollment_id: UUID) -> None:
    """Return a claimed enrollment to immediate eligibility if dispatch fails."""
    async with celery_session() as db:
        service = EnrollmentService(db)
        await service.requeue_claimed_enrollment(enrollment_id)
        await db.commit()
