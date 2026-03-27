import json
import logging
import time
import urllib.request
from uuid import uuid4

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

_DEBUG_LOG_PATH = "/Users/admin/projects/jooba/.cursor/debug-65ee5d.log"
_DEBUG_SESSION_ID = "65ee5d"
_DEBUG_INGEST_URL = "http://host.docker.internal:7596/ingest/248d38e7-8c89-455d-827c-d1995e609387"


def _write_debug_log(
    *,
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
) -> None:
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "id": f"log_{int(time.time() * 1000)}_{uuid4().hex[:8]}",
        "timestamp": int(time.time() * 1000),
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
    }
    wrote_local = False
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as debug_file:
            debug_file.write(json.dumps(payload, default=str) + "\n")
        wrote_local = True
    except Exception:
        wrote_local = False

    if wrote_local:
        return

    try:
        request = urllib.request.Request(
            _DEBUG_INGEST_URL,
            data=json.dumps(payload, default=str).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Debug-Session-Id": _DEBUG_SESSION_ID,
            },
            method="POST",
        )
        urllib.request.urlopen(request, timeout=1).read()
    except Exception:
        return


def _extract_reply_to_message_id(message_obj: dict) -> str | None:
    """Extract parent message id from webhook payload when available."""
    direct = message_obj.get("reply_to_message_id")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    in_reply_to = message_obj.get("in_reply_to")
    if isinstance(in_reply_to, str) and in_reply_to.strip():
        return in_reply_to.strip()

    headers = message_obj.get("headers")
    if isinstance(headers, list):
        for header in headers:
            if not isinstance(header, dict):
                continue
            name = (header.get("name") or "").lower()
            if name in {"in-reply-to", "in_reply_to"}:
                value = header.get("value")
                if isinstance(value, str) and value.strip():
                    return value.strip().strip("<>")

    return None


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
    run_id = f"webhook-{int(time.time() * 1000)}-{uuid4().hex[:6]}"
    logger.info("Webhook received: %d bytes, sig=%s", len(raw_body), signature[:16] + "..." if signature else "(none)")
    # region agent log
    _write_debug_log(
        run_id=run_id,
        hypothesis_id="H1",
        location="app/api/webhooks.py:nylas_webhook:entry",
        message="Webhook endpoint hit",
        data={
            "bodyBytes": len(raw_body),
            "hasSignature": bool(signature),
            "contentType": request.headers.get("Content-Type", ""),
        },
    )
    # endregion

    webhook_secret = await _get_webhook_secret(db)
    secret_source = "env" if settings.nylas_webhook_secret else ("db" if webhook_secret else "none")
    # region agent log
    _write_debug_log(
        run_id=run_id,
        hypothesis_id="H2",
        location="app/api/webhooks.py:nylas_webhook:signature_context",
        message="Prepared signature verification context",
        data={
            "secretConfigured": bool(webhook_secret),
            "secretSource": secret_source,
            "hasSignature": bool(signature),
        },
    )
    # endregion
    if webhook_secret:
        if not signature:
            logger.warning("Webhook rejected: missing signature")
            # region agent log
            _write_debug_log(
                run_id=run_id,
                hypothesis_id="H2",
                location="app/api/webhooks.py:nylas_webhook:signature_reject",
                message="Rejected webhook before processing",
                data={"reason": "missing_signature"},
            )
            # endregion
            raise HTTPException(status_code=401, detail="Missing webhook signature")
        nylas_client = NylasClient()
        if not nylas_client.verify_webhook_signature(raw_body, signature, webhook_secret):
            logger.warning("Webhook rejected: invalid signature")
            # region agent log
            _write_debug_log(
                run_id=run_id,
                hypothesis_id="H2",
                location="app/api/webhooks.py:nylas_webhook:signature_reject",
                message="Rejected webhook before processing",
                data={"reason": "invalid_signature"},
            )
            # endregion
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        logger.info("Webhook signature verified OK")
    else:
        logger.info("Webhook: no secret configured, skipping signature check")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("Webhook rejected: malformed JSON")
        # region agent log
        _write_debug_log(
            run_id=run_id,
            hypothesis_id="H3",
            location="app/api/webhooks.py:nylas_webhook:json_parse",
            message="Webhook payload rejected as malformed JSON",
            data={"bodyBytes": len(raw_body)},
        )
        # endregion
        raise HTTPException(status_code=400, detail="Malformed webhook payload")

    event_type = body.get("type", "unknown")
    # Nylas v3 CloudEvents envelope: body["data"]["object"] contains the message.
    data_section = body.get("data", {})
    message_obj = data_section.get("object", {}) if isinstance(data_section, dict) else {}
    from_list = message_obj.get("from", [])
    sender_email = ""
    if isinstance(from_list, list) and from_list:
        sender_email = from_list[0].get("email", "")
    reply_to_message_id = _extract_reply_to_message_id(message_obj)
    # region agent log
    _write_debug_log(
        run_id=run_id,
        hypothesis_id="H3",
        location="app/api/webhooks.py:nylas_webhook:payload_extract",
        message="Extracted webhook payload envelope",
        data={
            "eventType": event_type,
            "hasDataObject": isinstance(data_section, dict) and isinstance(data_section.get("object"), dict),
            "hasMessageId": bool(message_obj.get("id")),
            "hasThreadId": bool(message_obj.get("thread_id")),
            "fromCount": len(from_list) if isinstance(from_list, list) else 0,
            "hasReplyToMessageId": bool(reply_to_message_id),
        },
    )
    # endregion

    message_data = {
        "message_id": message_obj.get("id"),
        "thread_id": message_obj.get("thread_id"),
        "sender_email": sender_email,
        "subject": message_obj.get("subject", ""),
        "body_html": message_obj.get("body", ""),
        "body_text": message_obj.get("snippet", ""),
        "reply_to_message_id": reply_to_message_id,
        "_debug_run_id": run_id,
    }
    logger.info(
        "Webhook parsed: type=%s message_id=%s thread_id=%s from=%s subject=%r",
        event_type,
        message_data["message_id"],
        message_data["thread_id"],
        message_data["sender_email"],
        (message_data["subject"] or "")[:60],
    )
    # region agent log
    _write_debug_log(
        run_id=run_id,
        hypothesis_id="H4",
        location="app/api/webhooks.py:nylas_webhook:dispatch_service",
        message="Dispatching message data to EmailService.process_webhook",
        data={
            "hasMessageId": bool(message_data["message_id"]),
            "hasThreadId": bool(message_data["thread_id"]),
            "hasSenderEmail": bool(message_data["sender_email"]),
            "hasReplyToMessageId": bool(message_data["reply_to_message_id"]),
        },
    )
    # endregion

    service = EmailService(db)
    try:
        await service.process_webhook(message_data)
    except Exception as exc:
        logger.exception(
            "Webhook processing failed for message_id=%s, returning 200 to prevent Nylas retry",
            message_data.get("message_id"),
        )
        # region agent log
        _write_debug_log(
            run_id=run_id,
            hypothesis_id="H5",
            location="app/api/webhooks.py:nylas_webhook:service_exception",
            message="EmailService raised during webhook processing",
            data={"errorType": exc.__class__.__name__},
        )
        # endregion
    else:
        # region agent log
        _write_debug_log(
            run_id=run_id,
            hypothesis_id="H4",
            location="app/api/webhooks.py:nylas_webhook:service_completed",
            message="EmailService completed without exception",
            data={},
        )
        # endregion

    return {"status": "ok"}


@router.get("/webhook")
async def nylas_webhook_challenge(challenge: str = ""):
    """Nylas webhook verification -- echo the challenge parameter as plain text."""
    return PlainTextResponse(challenge)
