import hashlib
import hmac
import logging
from collections.abc import Mapping
from dataclasses import dataclass

from nylas import Client as NylasSDK
from nylas.models.errors import NylasApiError, NylasOAuthError, NylasSdkTimeoutError

from app.core.config import settings
from app.services.exceptions import PermanentError, ProviderRateLimited, TransientError

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

    def get_auth_url(self, state: str | None = None) -> str:
        """Generate Nylas OAuth URL for email account connection."""
        try:
            payload = {
                "client_id": settings.nylas_client_id,
                "redirect_uri": settings.nylas_callback_url,
            }
            if state:
                payload["state"] = state
            return self.client.auth.url_for_oauth2(payload)
        except Exception as exc:
            self._raise_domain_error(exc, operation="get auth url")

    def exchange_code_for_grant(self, code: str) -> dict[str, str]:
        """Exchange OAuth code for grant_id + email."""
        try:
            response = self.client.auth.exchange_code_for_token({
                "code": code,
                "client_id": settings.nylas_client_id,
                "redirect_uri": settings.nylas_callback_url,
            })
        except Exception as exc:
            self._raise_domain_error(exc, operation="exchange oauth code")
        provider = getattr(response, "provider", None) or "unknown"
        return {
            "grant_id": response.grant_id,
            "email": response.email,
            "provider": provider,
        }

    def send_email(
        self,
        grant_id: str,
        to: str,
        subject: str,
        body_html: str,
        reply_to_message_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SendResult:
        """Send an email through the connected account."""
        body: dict[str, object] = {
            "to": [{"email": to}],
            "subject": subject,
            "body": body_html,
        }
        if reply_to_message_id:
            body["reply_to_message_id"] = reply_to_message_id

        try:
            overrides: dict[str, object] | None = None
            if idempotency_key:
                overrides = {"headers": {"Idempotency-Key": idempotency_key}}
            response = self.client.messages.send(
                grant_id,
                request_body=body,
                overrides=overrides,
            )
            msg = response.data
            return SendResult(
                message_id=msg.id,
                thread_id=msg.thread_id,
            )
        except Exception as exc:
            self._raise_domain_error(exc, operation="send email")

    def list_webhooks(self) -> list[dict[str, object]]:
        """List all registered webhooks for this application."""
        try:
            response = self.client.webhooks.list()
            return [
                {
                    "id": wh.id,
                    "webhook_url": wh.webhook_url,
                    "status": wh.status,
                    "trigger_types": wh.trigger_types,
                }
                for wh in response.data
            ]
        except Exception as exc:
            self._raise_domain_error(exc, operation="list webhooks")

    def create_webhook(self, webhook_url: str, trigger_types: list[str]) -> dict[str, str]:
        """Register a new webhook with Nylas. Returns id and secret."""
        try:
            response = self.client.webhooks.create(
                request_body={
                    "trigger_types": trigger_types,
                    "webhook_url": webhook_url,
                }
            )
            wh = response.data
            return {
                "id": wh.id,
                "webhook_secret": wh.webhook_secret,
            }
        except Exception as exc:
            self._raise_domain_error(exc, operation="register webhook")

    def delete_webhook(self, webhook_id: str) -> None:
        """Delete a registered webhook."""
        try:
            self.client.webhooks.destroy(webhook_id)
        except Exception as exc:
            self._raise_domain_error(exc, operation="delete webhook")

    def list_messages(self, grant_id: str, received_after: int, limit: int = 25) -> list[dict]:
        """Fetch recent messages from Nylas. Returns normalized dicts."""
        try:
            response = self.client.messages.list(
                grant_id,
                query_params={
                    "limit": limit,
                    "received_after": received_after,
                },
            )
        except Exception as exc:
            self._raise_domain_error(exc, operation="list messages")

        results = []
        for msg in response.data:
            sender_email = ""
            if msg.from_:
                first_from = msg.from_[0]
                if isinstance(first_from, dict):
                    sender_email = first_from.get("email", "")
                else:
                    sender_email = first_from.email or ""
            msg_date = msg.date if isinstance(msg.date, int) else getattr(msg, "date", 0) or 0
            results.append({
                "message_id": msg.id,
                "thread_id": msg.thread_id,
                "sender_email": sender_email,
                "subject": msg.subject or "",
                "body_html": msg.body or "",
                "body_text": msg.snippet or "",
                "date": msg_date,
            })
        return results

    def verify_webhook_signature(self, raw_body: bytes, signature: str, secret: str | None = None) -> bool:
        """Verify Nylas webhook signature using the provided secret."""
        signing_key = secret or settings.nylas_webhook_secret or settings.nylas_api_key
        if not signing_key:
            logger.error("verify_webhook_signature called without any signing key - rejecting")
            return False
        expected = hmac.new(
            signing_key.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _raise_domain_error(self, error: Exception, operation: str) -> None:
        if isinstance(error, (ProviderRateLimited, TransientError, PermanentError)):
            raise error

        if isinstance(error, NylasSdkTimeoutError):
            raise TransientError(f"Nylas {operation} timed out") from error

        if isinstance(error, NylasOAuthError):
            self._raise_if_rate_limited_or_auth_error(error, operation)
            sc = error.status_code
            if isinstance(sc, int) and 500 <= sc < 600:
                raise TransientError(f"Nylas {operation} oauth provider error: {error}") from error
            raise PermanentError(f"Nylas {operation} oauth error: {error}") from error

        if isinstance(error, NylasApiError):
            self._raise_if_rate_limited_or_auth_error(error, operation)
            sc = error.status_code
            if isinstance(sc, int) and 400 <= sc < 500:
                raise PermanentError(f"Nylas {operation} client error: {error}") from error
            if isinstance(sc, int) and 500 <= sc < 600:
                raise TransientError(f"Nylas {operation} provider error: {error}") from error
            raise TransientError(f"Nylas {operation} error: {error}") from error

        raise TransientError(f"Nylas {operation} error: {error}") from error

    def _raise_if_rate_limited_or_auth_error(
        self,
        error: NylasApiError | NylasOAuthError,
        operation: str,
    ) -> None:
        status_code = error.status_code
        if status_code == 429:
            raise ProviderRateLimited(self._retry_after_seconds(error.headers)) from error
        if status_code in {401, 403}:
            raise PermanentError(f"Nylas {operation} auth error: {error}") from error

    def _retry_after_seconds(self, headers: Mapping[str, str] | None) -> int:
        if not headers:
            return 60
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after is None:
            return 60
        try:
            return max(1, int(retry_after))
        except (TypeError, ValueError):
            return 60
