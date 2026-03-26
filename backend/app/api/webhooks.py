import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.integrations.nylas_client import NylasClient
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nylas", tags=["webhooks"])


@router.post("/webhook")
async def nylas_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive Nylas webhook notifications for new messages.

    Validates webhook signature before processing.
    Must return 200 quickly -- heavy processing dispatched to Celery.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Nylas-Signature", "")
    nylas_client = NylasClient()
    if signature and not nylas_client.verify_webhook_signature(raw_body, signature):
        logger.warning("Invalid Nylas webhook signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    body = json.loads(raw_body)

    # Nylas v3 webhook payload -- extract message data
    data = body.get("data", {})
    message_data = {
        "message_id": data.get("id"),
        "thread_id": data.get("thread_id"),
        "sender_email": "",
        "subject": data.get("subject", ""),
        "body_html": data.get("body", ""),
        "body_text": data.get("snippet", ""),
    }

    # Extract sender email from "from" field
    from_list = data.get("from", [])
    if from_list and isinstance(from_list, list):
        message_data["sender_email"] = from_list[0].get("email", "")

    service = EmailService(db)
    await service.process_webhook(message_data)

    return {"status": "ok"}


@router.get("/webhook")
async def nylas_webhook_challenge(challenge: str = ""):
    """Nylas webhook verification -- echo the challenge parameter."""
    return {"challenge": challenge}
