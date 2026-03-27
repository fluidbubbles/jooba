from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.nylas_connection_service as service_module
from app.core.config import settings
from app.services.nylas_connection_service import NylasConnectionService


def _service() -> NylasConnectionService:
    return NylasConnectionService(AsyncMock(), client=MagicMock())


def test_oauth_state_round_trip_valid(monkeypatch) -> None:
    service = _service()
    now = 1_700_000_000
    monkeypatch.setattr(service_module.time, "time", lambda: now)

    state = service.generate_oauth_state()

    assert service.validate_oauth_state(state) is True


def test_oauth_state_rejects_tampered_signature(monkeypatch) -> None:
    service = _service()
    now = 1_700_000_000
    monkeypatch.setattr(service_module.time, "time", lambda: now)
    state = service.generate_oauth_state()
    tampered = state[:-1] + ("0" if state[-1] != "0" else "1")

    assert service.validate_oauth_state(tampered) is False


def test_oauth_state_rejects_expired_token(monkeypatch) -> None:
    service = _service()
    issued_at = 1_700_000_000
    monkeypatch.setattr(service_module.time, "time", lambda: issued_at)
    state = service.generate_oauth_state()

    monkeypatch.setattr(
        service_module.time,
        "time",
        lambda: issued_at + service_module._OAUTH_STATE_TTL_SECONDS + 1,
    )

    assert service.validate_oauth_state(state) is False


def test_oauth_state_rejects_malformed_value() -> None:
    service = _service()
    assert service.validate_oauth_state("not:a:valid:shape") is False


# ---------------------------------------------------------------------------
# Decoupling tests — webhook registration must be separate from OAuth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_oauth_callback_does_not_register_webhook() -> None:
    """complete_oauth_callback must only persist the account.
    Webhook registration is a separate step; the route calls it explicitly."""
    service = _service()
    service._client.exchange_code_for_grant = MagicMock(
        return_value={"grant_id": "g-1", "email": "a@b.com", "provider": "google"}
    )
    service._repo.replace_single_account = AsyncMock()
    # list_webhooks is the first thing _ensure_webhook_registered calls.
    # If it is called here, the coupling is still present.
    service._client.list_webhooks = MagicMock(return_value=[])

    await service.complete_oauth_callback("oauth-code")

    service._client.list_webhooks.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_webhook_registered_is_public_and_callable_standalone() -> None:
    """ensure_webhook_registered must be a public method callable independently."""
    service = _service()
    service._client.list_webhooks = MagicMock(return_value=[])
    service._client.create_webhook = MagicMock(
        return_value={"id": "wh-1", "webhook_secret": "sec-abc"}
    )
    service._repo.set_webhook_secret = AsyncMock()

    # This will AttributeError if the method is still private (_ensure_webhook_registered).
    await service.ensure_webhook_registered()

    service._client.create_webhook.assert_called_once()
    service._repo.set_webhook_secret.assert_awaited_once_with("sec-abc")


@pytest.mark.asyncio
async def test_disconnect_deletes_webhook_from_nylas() -> None:
    """disconnect must remove the webhook from Nylas before deleting the account row."""
    service = _service()
    service._repo.delete_all = AsyncMock()
    webhook_url = settings.nylas_webhook_url
    service._client.list_webhooks = MagicMock(
        return_value=[
            {"id": "wh-99", "webhook_url": webhook_url, "status": "active", "trigger_types": []},
        ]
    )
    service._client.delete_webhook = MagicMock()

    await service.disconnect()

    service._client.delete_webhook.assert_called_once_with("wh-99")
