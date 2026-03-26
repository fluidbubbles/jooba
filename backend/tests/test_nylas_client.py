import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest
from nylas.models.errors import (
    NylasApiError,
    NylasApiErrorResponse,
    NylasApiErrorResponseData,
    NylasOAuthError,
    NylasOAuthErrorResponse,
    NylasSdkTimeoutError,
)

from app.core.config import settings
from app.integrations.nylas_client import NylasClient
from app.services.exceptions import PermanentError, ProviderRateLimited, TransientError

_SEND_EMAIL_KWARGS = {
    "grant_id": "grant_123",
    "to": "jane@example.com",
    "subject": "Hello",
    "body_html": "<p>Hi</p>",
}


def _patch_messages_send(client: NylasClient, side_effect: Exception):
    return patch.object(type(client.client.messages), "send", side_effect=side_effect)


def _api_error(
    status_code: int,
    message: str,
    headers: dict[str, str] | None = None,
) -> NylasApiError:
    return NylasApiError(
        api_error=NylasApiErrorResponse(
            request_id="req_123",
            error=NylasApiErrorResponseData(type="api_error", message=message),
        ),
        status_code=status_code,
        headers=headers or {},
    )


def _oauth_error(
    status_code: int | None,
    error_code: int,
    description: str,
) -> NylasOAuthError:
    return NylasOAuthError(
        oauth_error=NylasOAuthErrorResponse(
            error="oauth_error",
            error_code=error_code,
            error_description=description,
            error_uri="https://example.com/errors/oauth",
        ),
        status_code=status_code,
        headers={},
    )


class TestNylasClientErrorTranslation:
    def test_send_email_maps_429_to_provider_rate_limited(self):
        client = NylasClient()

        with _patch_messages_send(
            client,
            _api_error(
                status_code=429,
                message="Too many requests",
                headers={"Retry-After": "15"},
            ),
        ):
            with pytest.raises(ProviderRateLimited) as exc_info:
                client.send_email(**_SEND_EMAIL_KWARGS)

        assert exc_info.value.retry_after == 15

    def test_send_email_maps_401_to_permanent_error(self):
        client = NylasClient()

        with _patch_messages_send(
            client,
            _api_error(status_code=401, message="Invalid credentials"),
        ):
            with pytest.raises(PermanentError) as exc_info:
                client.send_email(**_SEND_EMAIL_KWARGS)

        assert exc_info.value.code == "PERMANENT_ERROR"

    def test_send_email_maps_5xx_to_transient_error(self):
        client = NylasClient()

        with _patch_messages_send(
            client,
            _api_error(status_code=503, message="Upstream unavailable"),
        ):
            with pytest.raises(TransientError) as exc_info:
                client.send_email(**_SEND_EMAIL_KWARGS)

        assert exc_info.value.code == "TRANSIENT_ERROR"

    def test_send_email_maps_timeout_to_transient_error(self):
        client = NylasClient()

        with _patch_messages_send(
            client,
            NylasSdkTimeoutError(url="https://api.us.nylas.com/v3/grants/grant/messages/send", timeout=30),
        ):
            with pytest.raises(TransientError) as exc_info:
                client.send_email(**_SEND_EMAIL_KWARGS)

        assert exc_info.value.code == "TRANSIENT_ERROR"

    def test_exchange_code_maps_oauth_auth_error_to_permanent_error(self):
        client = NylasClient()
        client.client.auth.exchange_code_for_token = MagicMock(
            side_effect=_oauth_error(
                status_code=401,
                error_code=401,
                description="Invalid oauth code",
            )
        )

        with pytest.raises(PermanentError) as exc_info:
            client.exchange_code_for_grant("oauth_code")

        assert exc_info.value.code == "PERMANENT_ERROR"

    def test_exchange_code_does_not_treat_oauth_error_code_as_http_status(self):
        client = NylasClient()
        client.client.auth.exchange_code_for_token = MagicMock(
            side_effect=_oauth_error(
                status_code=None,
                error_code=429,
                description="Provider-specific oauth error code",
            )
        )

        with pytest.raises(PermanentError) as exc_info:
            client.exchange_code_for_grant("oauth_code")

        assert exc_info.value.code == "PERMANENT_ERROR"


class TestNylasWebhookVerification:
    def test_verify_webhook_signature_accepts_valid_signature(self, monkeypatch):
        monkeypatch.setattr(settings, "nylas_webhook_secret", "webhook-secret")
        client = NylasClient()
        raw_body = b'{"event":"message.created"}'
        signature = hmac.new(
            b"webhook-secret",
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        assert client.verify_webhook_signature(raw_body, signature) is True

    def test_verify_webhook_signature_rejects_empty_secret(self, monkeypatch):
        monkeypatch.setattr(settings, "nylas_webhook_secret", "")
        client = NylasClient()
        assert client.verify_webhook_signature(b"{}", "abc") is False
