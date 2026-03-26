import asyncio
import logging
import time

from app.celery_app import celery_app
from app.database import celery_session
from app.integrations.nylas_client import NylasClient
from app.repositories.nylas_account_repo import NylasAccountRepository
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

# In-memory tracker — resets on worker restart, which is fine (dedup in service handles overlap)
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

    async with celery_session() as db:
        account_repo = NylasAccountRepository(db)
        account = await account_repo.get_first()
        if not account:
            return

        grant_id = account.grant_id
        account_email = account.email.lower()

        # First run: look back 5 minutes
        if _last_poll_ts == 0:
            _last_poll_ts = int(time.time()) - 300

        nylas = NylasClient()
        try:
            response = nylas.client.messages.list(
                grant_id,
                query_params={
                    "limit": 25,
                    "received_after": _last_poll_ts,
                },
            )
        except Exception:
            logger.exception("Nylas poll failed")
            return

        messages = response.data
        if not messages:
            return

        logger.info("Poller found %d message(s) since ts=%d", len(messages), _last_poll_ts)

        # Advance watermark first — use message timestamps
        max_ts = 0
        for msg in messages:
            msg_date = msg.date if isinstance(msg.date, int) else getattr(msg, "date", 0) or 0
            if msg_date > max_ts:
                max_ts = msg_date
        if max_ts > _last_poll_ts:
            _last_poll_ts = max_ts

        service = EmailService(db)
        for msg in messages:
            sender_email = ""
            if msg.from_:
                first_from = msg.from_[0]
                if isinstance(first_from, dict):
                    sender_email = first_from.get("email", "")
                else:
                    sender_email = first_from.email or ""

            # Skip our own outbound sends
            if sender_email.lower() == account_email:
                continue

            logger.info("Poller processing: id=%s from=%s subj=%s", msg.id, sender_email, (msg.subject or "")[:40])

            message_data = {
                "message_id": msg.id,
                "thread_id": msg.thread_id,
                "sender_email": sender_email,
                "subject": msg.subject or "",
                "body_html": msg.body or "",
                "body_text": msg.snippet or "",
            }

            try:
                await service.process_webhook(message_data)
                await db.commit()
            except Exception:
                logger.exception("Poller: failed processing message %s", msg.id)
                await db.rollback()
