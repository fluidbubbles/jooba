import asyncio
import logging
import time

from app.celery_app import celery_app
from app.database import celery_session
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

# In-memory watermark — resets on worker restart, which is fine (dedup in service handles overlap)
_last_poll_ts: int = 0


@celery_app.task(
    name="app.tasks.nylas_poller.poll_nylas_messages",
    bind=True,
    queue="default",
    soft_time_limit=20,
)
def poll_nylas_messages(self) -> None:
    """Poll Nylas for new messages and process them like webhooks."""
    asyncio.run(_poll())


async def _poll() -> None:
    global _last_poll_ts  # noqa: PLW0603

    # First run: look back 5 minutes
    if _last_poll_ts == 0:
        _last_poll_ts = int(time.time()) - 300

    async with celery_session() as db:
        service = EmailService(db)
        _last_poll_ts = await service.poll_new_messages(_last_poll_ts)
