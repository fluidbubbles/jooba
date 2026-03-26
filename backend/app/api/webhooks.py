import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import get_db
from app.integrations.nylas_client import NylasClient
from app.repositories.nylas_account_repo import NylasAccountRepository
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nylas", tags=["webhooks"])


async def _get_webhook_secret(db: AsyncSession) -> str:
    """Get webhook secret: env var takes precedence, then DB-stored secret."""
    if settings.nylas_webhook_secret:
        return settings.nylas_webhook_secret
    account = await NylasAccountRepository(db).get_first()
    return (account.webhook_secret or "") if account else ""


@router.post("/webhook")
async def nylas_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive Nylas webhook notifications for new messages.

    Validates webhook signature before processing.
    Must return 200 quickly — heavy processing dispatched to Celery.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Nylas-Signature", "")

    webhook_secret = await _get_webhook_secret(db)
    if webhook_secret:
        if not signature:
            logger.warning("Missing Nylas webhook signature")
            raise HTTPException(status_code=401, detail="Missing webhook signature")
        nylas_client = NylasClient()
        if not nylas_client.verify_webhook_signature(raw_body, signature, webhook_secret):
            logger.warning("Invalid Nylas webhook signature")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("Malformed webhook payload, discarding")
        return {"status": "ok"}

    # Nylas v3 webhook payload — extract message data
    data = body.get("data", {})
    from_list = data.get("from", [])
    sender_email = ""
    if isinstance(from_list, list) and from_list:
        sender_email = from_list[0].get("email", "")

    message_data = {
        "message_id": data.get("id"),
        "thread_id": data.get("thread_id"),
        "sender_email": sender_email,
        "subject": data.get("subject", ""),
        "body_html": data.get("body", ""),
        "body_text": data.get("snippet", ""),
    }

    service = EmailService(db)
    try:
        await service.process_webhook(message_data)
    except Exception:
        logger.exception("Webhook processing failed, returning 200 to prevent Nylas retry")

    return {"status": "ok"}


@router.get("/webhook")
async def nylas_webhook_challenge(challenge: str = ""):
    """Nylas webhook verification -- echo the challenge parameter as plain text."""
    return PlainTextResponse(challenge)
