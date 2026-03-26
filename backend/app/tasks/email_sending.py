import asyncio
import logging
from uuid import UUID

from celery import Task

from app.celery_app import celery_app
from app.database import celery_session
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import PermanentError, ProviderRateLimited, TransientError

logger = logging.getLogger(__name__)

TRANSIENT_MAX_RETRIES = 5
TRANSIENT_BACKOFFS = [30, 60, 120, 240, 480]


def _transient_backoff_seconds(retries: int) -> int:
    return TRANSIENT_BACKOFFS[min(retries, len(TRANSIENT_BACKOFFS) - 1)]


def _pause_enrollment_safe(enrollment_id: str, msg: str, *msg_args: object) -> None:
    try:
        asyncio.run(_pause_enrollment(enrollment_id))
    except Exception:
        logger.exception(msg, *msg_args)


@celery_app.task(
    name="app.tasks.email_sending.send_sequence_email",
    bind=True,
    acks_late=True,
    queue="email",
    soft_time_limit=60,
)
def send_sequence_email(self: Task, enrollment_id: str) -> None:
    """Celery task entry point: delegates to service, with retry policy per exception type."""
    try:
        asyncio.run(_send(enrollment_id))
    except ProviderRateLimited as e:
        logger.warning("Rate limited, retrying in %ds", e.retry_after)
        raise self.retry(countdown=e.retry_after, max_retries=None)  # unbounded: trust provider backoff
    except TransientError as e:
        retries = self.request.retries
        if retries >= TRANSIENT_MAX_RETRIES:
            logger.error(
                "Transient error after %d retries, pausing enrollment %s",
                retries, enrollment_id,
            )
            _pause_enrollment_safe(
                enrollment_id, "Failed to pause enrollment after max retries"
            )
            return
        backoff = _transient_backoff_seconds(retries)
        logger.warning(
            "Transient error, retry %d/%d in %ds: %s",
            retries + 1, TRANSIENT_MAX_RETRIES, backoff, e,
        )
        raise self.retry(countdown=backoff, max_retries=TRANSIENT_MAX_RETRIES)
    except PermanentError as e:
        logger.error("Permanent error for enrollment %s: %s", enrollment_id, e)
        _pause_enrollment_safe(
            enrollment_id, "Failed to pause enrollment after permanent error"
        )
    except Exception:
        logger.exception("Unexpected error for enrollment %s", enrollment_id)
        retries = self.request.retries
        if retries >= TRANSIENT_MAX_RETRIES:
            _pause_enrollment_safe(
                enrollment_id,
                "Failed to pause enrollment %s after unexpected error",
                enrollment_id,
            )
            return
        backoff = _transient_backoff_seconds(retries)
        raise self.retry(countdown=backoff, max_retries=TRANSIENT_MAX_RETRIES)


async def _send(enrollment_id: str) -> None:
    async with celery_session() as db:
        service = EnrollmentService(db)
        await service.send_email_for_enrollment(UUID(enrollment_id))
        await db.commit()


async def _pause_enrollment(enrollment_id: str) -> None:
    async with celery_session() as db:
        service = EnrollmentService(db)
        await service.mark_paused(UUID(enrollment_id))
        await db.commit()
