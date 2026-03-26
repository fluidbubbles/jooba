import hashlib
import hmac
import logging
from dataclasses import dataclass

from nylas import Client as NylasSDK

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    message_id: str
    thread_id: str


class NylasClient:
    def __init__(self) -> None:
        self.client = NylasSDK(
            api_key=settings.nylas_api_key,
        )

    def get_auth_url(self) -> str:
        """Generate Nylas OAuth URL for email account connection."""
        return self.client.auth.url_for_oauth2({
            "client_id": settings.nylas_client_id,
            "redirect_uri": settings.nylas_callback_url,
        })

    def exchange_code_for_grant(self, code: str) -> dict:
        """Exchange OAuth code for grant_id + email."""
        response = self.client.auth.exchange_code_for_token({
            "code": code,
            "client_id": settings.nylas_client_id,
            "redirect_uri": settings.nylas_callback_url,
        })
        return {
            "grant_id": response.grant_id,
            "email": response.email,
        }

    def send_email(
        self,
        grant_id: str,
        to: str,
        subject: str,
        body_html: str,
        reply_to_message_id: str | None = None,
    ) -> SendResult:
        """Send an email through the connected account."""
        body = {
            "to": [{"email": to}],
            "subject": subject,
            "body": body_html,
        }
        if reply_to_message_id:
            body["reply_to_message_id"] = reply_to_message_id

        response = self.client.messages.send(grant_id, request_body=body)
        msg = response.data
        return SendResult(
            message_id=msg.id,
            thread_id=msg.thread_id,
        )

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        """Verify Nylas webhook signature using the webhook-specific secret."""
        if not settings.nylas_webhook_secret:
            logger.error("verify_webhook_signature called with empty nylas_webhook_secret — rejecting")
            return False
        expected = hmac.new(
            settings.nylas_webhook_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
