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


def _schedule_transient_retry(task: Task) -> None:
    backoff = _transient_backoff_seconds(task.request.retries)
    raise task.retry(countdown=backoff, max_retries=TRANSIENT_MAX_RETRIES)


def _pause_single_enrollment_or_raise(
    enrollment_id: str,
    trigger: str,
    msg: str,
    *msg_args: object,
) -> None:
    try:
        asyncio.run(_pause_enrollment(enrollment_id, trigger))
        return
    except Exception:
        logger.exception(msg, *msg_args)
        try:
            asyncio.run(_requeue_claimed_enrollment(enrollment_id))
            logger.warning(
                "Requeued enrollment %s after pause failure to avoid stranded claim",
                enrollment_id,
            )
        except Exception:
            logger.exception(
                "Failed to requeue enrollment %s after pause failure",
                enrollment_id,
            )
    raise RuntimeError(f"Failed to pause enrollment {enrollment_id}")


def _pause_all_active_enrollments_or_raise(
    trigger: str, msg: str, *msg_args: object
) -> None:
    try:
        paused_count = asyncio.run(_pause_all_active_enrollments(trigger))
        logger.warning(
            "Paused %d active enrollment(s) due to account-level permanent error",
            paused_count,
        )
    except Exception:
        logger.exception(msg, *msg_args)
        raise RuntimeError("Failed to pause active enrollments")


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
                retries,
                enrollment_id,
            )
            _pause_single_enrollment_or_raise(
                enrollment_id,
                "max_retries_exhausted",
                "Failed to pause enrollment after max retries",
            )
            return
        backoff = _transient_backoff_seconds(retries)
        logger.warning(
            "Transient error, retry %d/%d in %ds: %s",
            retries + 1,
            TRANSIENT_MAX_RETRIES,
            backoff,
            e,
        )
        _schedule_transient_retry(self)
    except PermanentError as e:
        logger.error("Permanent error for enrollment %s: %s", enrollment_id, e)
        if "auth error" in str(e).lower():
            _pause_all_active_enrollments_or_raise(
                "provider_auth_revoked",
                "Failed to pause active enrollments after provider auth error",
            )
            return
        _pause_single_enrollment_or_raise(
            enrollment_id,
            "permanent_error",
            "Failed to pause enrollment after permanent error",
        )
    except Exception:
        logger.exception("Unexpected error for enrollment %s", enrollment_id)
        if self.request.retries >= TRANSIENT_MAX_RETRIES:
            _pause_single_enrollment_or_raise(
                enrollment_id,
                "unexpected_error",
                "Failed to pause enrollment %s after unexpected error",
                enrollment_id,
            )
            return
        _schedule_transient_retry(self)


async def _send(enrollment_id: str) -> None:
    async with celery_session() as db:
        service = EnrollmentService(db)
        await service.send_email_for_enrollment(UUID(enrollment_id))
        await db.commit()


async def _pause_enrollment(enrollment_id: str, trigger: str) -> None:
    async with celery_session() as db:
        service = EnrollmentService(db)
        await service.mark_paused(UUID(enrollment_id), trigger=trigger)
        await db.commit()


async def _requeue_claimed_enrollment(enrollment_id: str) -> None:
    async with celery_session() as db:
        service = EnrollmentService(db)
        await service.requeue_claimed_enrollment(UUID(enrollment_id))
        await db.commit()


async def _pause_all_active_enrollments(trigger: str) -> int:
    async with celery_session() as db:
        service = EnrollmentService(db)
        paused_count = await service.mark_all_active_paused(trigger=trigger)
        await db.commit()
        return paused_count
