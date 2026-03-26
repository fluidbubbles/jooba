from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.exceptions import ProviderRateLimited, TransientError
from app.services.nylas_connection_service import NylasConnectionService

_REDIRECT_STATUS = frozenset({302, 307})


async def _connect_account(client: AsyncClient) -> None:
    with (
        patch(
            "app.services.nylas_connection_service.NylasConnectionService.validate_oauth_state",
            return_value=True,
        ),
        patch(
            "app.integrations.nylas_client.NylasClient.exchange_code_for_grant",
            return_value={
                "grant_id": "grant_123",
                "email": "owner@example.com",
                "provider": "google",
            },
        ),
    ):
        response = await client.get(
            "/api/nylas/callback",
            params={"code": "oauth-code", "state": "signed-state"},
        )
    assert response.status_code in _REDIRECT_STATUS


@pytest.mark.asyncio
async def test_status_disconnected_by_default(client: AsyncClient) -> None:
    response = await client.get("/api/nylas/status")

    assert response.status_code == 200
    assert response.json()["connected"] is False


@pytest.mark.asyncio
async def test_auth_url_returns_service_generated_url(client: AsyncClient) -> None:
    with patch(
        "app.services.nylas_connection_service.NylasConnectionService.get_auth_url",
        return_value="https://auth.example.com/nylas",
    ):
        response = await client.get("/api/nylas/auth-url")

    assert response.status_code == 200
    assert response.json() == {"url": "https://auth.example.com/nylas"}


@pytest.mark.asyncio
async def test_callback_persists_account_and_status_reports_connected(client: AsyncClient) -> None:
    await _connect_account(client)

    status_response = await client.get("/api/nylas/status")
    payload = status_response.json()

    assert status_response.status_code == 200
    assert payload["connected"] is True
    assert payload["email"] == "owner@example.com"
    assert payload["provider"] == "google"


@pytest.mark.asyncio
async def test_callback_redirects_when_provider_returns_error(client: AsyncClient) -> None:
    response = await client.get(
        "/api/nylas/callback",
        params={"error": "access_denied"},
    )

    assert response.status_code in _REDIRECT_STATUS
    assert response.headers["location"].endswith("/settings?error=oauth_denied")


@pytest.mark.asyncio
async def test_callback_rejects_invalid_state(client: AsyncClient) -> None:
    with patch(
        "app.services.nylas_connection_service.NylasConnectionService.validate_oauth_state",
        return_value=False,
    ):
        response = await client.get(
            "/api/nylas/callback",
            params={"code": "oauth-code", "state": "invalid-state"},
        )

    assert response.status_code in _REDIRECT_STATUS
    assert response.headers["location"].endswith("/settings?error=invalid_state")


@pytest.mark.asyncio
async def test_callback_uses_real_state_validation(client: AsyncClient) -> None:
    valid_state = NylasConnectionService(AsyncMock()).generate_oauth_state()
    with patch(
        "app.integrations.nylas_client.NylasClient.exchange_code_for_grant",
        return_value={
            "grant_id": "grant_real_state",
            "email": "real-state@example.com",
            "provider": "google",
        },
    ):
        response = await client.get(
            "/api/nylas/callback",
            params={"code": "oauth-code", "state": valid_state},
        )

    assert response.status_code in _REDIRECT_STATUS
    assert response.headers["location"].endswith("/settings?connected=true")


@pytest.mark.asyncio
async def test_callback_redirects_when_provider_rate_limited(client: AsyncClient) -> None:
    with (
        patch(
            "app.services.nylas_connection_service.NylasConnectionService.validate_oauth_state",
            return_value=True,
        ),
        patch(
            "app.integrations.nylas_client.NylasClient.exchange_code_for_grant",
            side_effect=ProviderRateLimited(30),
        ),
    ):
        response = await client.get(
            "/api/nylas/callback",
            params={"code": "oauth-code", "state": "signed-state"},
        )

    assert response.status_code in _REDIRECT_STATUS
    assert response.headers["location"].endswith("/settings?error=provider_rate_limited")


@pytest.mark.asyncio
async def test_callback_redirects_when_provider_is_temporarily_unavailable(
    client: AsyncClient,
) -> None:
    with (
        patch(
            "app.services.nylas_connection_service.NylasConnectionService.validate_oauth_state",
            return_value=True,
        ),
        patch(
            "app.integrations.nylas_client.NylasClient.exchange_code_for_grant",
            side_effect=TransientError("transient failure"),
        ),
    ):
        response = await client.get(
            "/api/nylas/callback",
            params={"code": "oauth-code", "state": "signed-state"},
        )

    assert response.status_code in _REDIRECT_STATUS
    assert response.headers["location"].endswith("/settings?error=auth_temporary")


@pytest.mark.asyncio
async def test_disconnect_clears_connected_account(client: AsyncClient) -> None:
    await _connect_account(client)

    disconnect_response = await client.delete("/api/nylas/disconnect")
    status_response = await client.get("/api/nylas/status")

    assert disconnect_response.status_code == 200
    assert disconnect_response.json() == {"status": "disconnected"}
    assert status_response.json()["connected"] is False
