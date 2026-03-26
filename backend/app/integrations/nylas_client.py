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

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        """Verify Nylas webhook signature.

        Prefer `nylas_webhook_secret`, but fall back to `nylas_api_key` for
        setups that use the API key as webhook signing secret.
        """
        secret = settings.nylas_webhook_secret or settings.nylas_api_key
        if not secret:
            logger.error(
                "verify_webhook_signature called without webhook secret/api key - rejecting"
            )
            return False
        if not settings.nylas_webhook_secret:
            logger.warning(
                "nylas_webhook_secret not set; falling back to nylas_api_key for webhook verification"
            )
        expected = hmac.new(
            secret.encode(),
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
