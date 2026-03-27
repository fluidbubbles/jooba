"""Regression tests for the Nylas webhook endpoint.

Reproduces the root-cause bug where message fields were read from body["data"]
instead of the correct Nylas v3 CloudEvents path body["data"]["object"].
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nylas_v3_payload(
    message_id: str = "msg-abc",
    thread_id: str = "thr-xyz",
    sender_email: str = "candidate@example.com",
    subject: str = "Re: Hello",
    body: str = "<p>Interested!</p>",
    snippet: str = "Interested!",
) -> bytes:
    """Build a realistic Nylas v3 CloudEvents webhook payload."""
    payload = {
        "specversion": "1.0",
        "type": "message.created",
        "source": "/nylas/us-east-1",
        "id": "delivery-001",
        "time": 1700000000,
        "webhook_delivery_attempt": 1,
        "data": {
            "application_id": "app-001",
            "object": {           # ← message lives here, NOT at data root
                "id": message_id,
                "grant_id": "grant-001",
                "thread_id": thread_id,
                "from": [{"name": "Candidate", "email": sender_email}],
                "subject": subject,
                "body": body,
                "snippet": snippet,
            },
        },
    }
    return json.dumps(payload).encode()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_extracts_message_from_data_object(client):
    """Regression: message fields must be read from body['data']['object'],
    not body['data'].  Before the fix all fields were None / empty, causing
    _match_to_enrollment to always return None and silently discard the event."""
    captured: list[dict] = []

    async def fake_process_webhook(data: dict) -> None:
        captured.append(data)

    with (
        patch(
            "app.api.webhooks._get_webhook_secret",
            new=AsyncMock(return_value=""),   # skip signature validation
        ),
        patch.object(
            __import__(
                "app.services.email_service",
                fromlist=["EmailService"],
            ).EmailService,
            "process_webhook",
            side_effect=fake_process_webhook,
        ),
    ):
        response = await client.post(
            "/api/nylas/webhook",
            content=_nylas_v3_payload(),
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert len(captured) == 1, "process_webhook should have been called once"
    data = captured[0]
    assert data["message_id"] == "msg-abc"
    assert data["thread_id"] == "thr-xyz"
    assert data["sender_email"] == "candidate@example.com"
    assert data["subject"] == "Re: Hello"
    assert data["body_html"] == "<p>Interested!</p>"
    assert data["body_text"] == "Interested!"


@pytest.mark.asyncio
async def test_webhook_challenge_returns_plain_text(client):
    """GET /api/nylas/webhook?challenge=abc must echo the challenge as plain text."""
    response = await client.get("/api/nylas/webhook?challenge=test-challenge-123")
    assert response.status_code == 200
    assert response.text == "test-challenge-123"
    assert "text/plain" in response.headers["content-type"]
