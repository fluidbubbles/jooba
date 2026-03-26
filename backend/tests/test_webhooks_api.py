"""Integration tests for webhook endpoints (Plan 5 — Reply Capture).

Covers: challenge echo, deduplication, unmatched webhooks, outbound detection,
sender fallback, mark_replied idempotency, and malformed payloads.
"""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RECRUITER_EMAIL = "recruiter@ramp.com"


async def _create_active_sequence(client: AsyncClient) -> str:
    """Create a sequence, activate it, return its id."""
    seq = await client.post("/api/sequences", json={
        "name": "Webhook Test Sequence",
        "steps": [{"subject": "Hi {{first_name}}", "body_html": "<p>Hello</p>", "delay": 0}],
    })
    assert seq.status_code == 201
    seq_id = seq.json()["id"]

    activate = await client.put(f"/api/sequences/{seq_id}/status", json={"status": "active"})
    assert activate.status_code == 200
    return seq_id


async def _enroll_candidate(
    client: AsyncClient, seq_id: str, email: str, first_name: str = "Jane",
) -> dict:
    """Enroll a single candidate and return the enrollment list item."""
    resp = await client.post(f"/api/sequences/{seq_id}/enroll", json={
        "candidates": [{"email": email, "first_name": first_name}],
    })
    assert resp.status_code == 201

    enrollments = await client.get(f"/api/sequences/{seq_id}/enrollments")
    assert enrollments.status_code == 200
    items = enrollments.json()["items"]
    for item in items:
        if item["candidate_email"] == email:
            return item
    raise AssertionError(f"Enrollment for {email} not found")


async def _insert_nylas_account(
    session_factory: async_sessionmaker[AsyncSession],
    email: str = RECRUITER_EMAIL,
) -> None:
    """Ensure a Nylas account exists for direction detection.

    If a real account already exists, returns its email instead.
    """
    async with session_factory() as db:
        existing = await db.execute(text("SELECT email FROM nylas_accounts LIMIT 1"))
        row = existing.scalar_one_or_none()
        if row:
            return row
        await db.execute(text(
            "INSERT INTO nylas_accounts (id, grant_id, email, provider, connected_at) "
            "VALUES (gen_random_uuid(), 'mock-grant', :email, 'mock', NOW())"
        ), {"email": email})
        await db.commit()
        return email


async def _seed_outbound_event(
    session_factory: async_sessionmaker[AsyncSession],
    enrollment_id: str,
    thread_id: str,
    message_id: str = "outbound-msg-001",
) -> None:
    """Insert an outbound email event so thread matching works for inbound webhooks."""
    async with session_factory() as db:
        await db.execute(text(
            "INSERT INTO email_events "
            "(id, enrollment_id, direction, subject, nylas_message_id, nylas_thread_id, "
            " is_manual_reply, created_at) "
            "VALUES (gen_random_uuid(), :enrollment_id, 'outbound', 'Hi', :message_id, "
            " :thread_id, false, NOW())"
        ), {
            "enrollment_id": enrollment_id,
            "message_id": message_id,
            "thread_id": thread_id,
        })
        await db.commit()


def _webhook_payload(
    *,
    message_id: str = "msg-abc-123",
    thread_id: str = "thread-xyz-456",
    sender_email: str = "jane@example.com",
    subject: str = "Re: Hi Jane",
    body: str = "<p>Sounds great!</p>",
    snippet: str = "Sounds great!",
) -> dict:
    """Build a Nylas v3 webhook payload."""
    return {
        "data": {
            "id": message_id,
            "thread_id": thread_id,
            "from": [{"email": sender_email}],
            "subject": subject,
            "body": body,
            "snippet": snippet,
        },
    }


async def _count_email_events(
    session_factory: async_sessionmaker[AsyncSession],
    enrollment_id: str | None = None,
    direction: str | None = None,
) -> int:
    """Count email events, optionally filtered by enrollment and direction."""
    async with session_factory() as db:
        where_clauses = []
        params: dict = {}
        if enrollment_id:
            where_clauses.append("enrollment_id = :enrollment_id")
            params["enrollment_id"] = enrollment_id
        if direction:
            where_clauses.append("direction = :direction")
            params["direction"] = direction
        where = " AND ".join(where_clauses) if where_clauses else "TRUE"
        result = await db.execute(
            text(f"SELECT COUNT(*) FROM email_events WHERE {where}"),  # noqa: S608
            params,
        )
        return result.scalar_one()


async def _get_enrollment_status(
    session_factory: async_sessionmaker[AsyncSession],
    enrollment_id: str,
) -> str:
    """Read current enrollment status directly from DB."""
    async with session_factory() as db:
        result = await db.execute(
            text("SELECT status FROM enrollments WHERE id = :id"),
            {"id": enrollment_id},
        )
        return result.scalar_one()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWebhookChallenge:
    """Test 1: Webhook challenge endpoint."""

    @pytest.mark.asyncio
    async def test_echo_challenge(self, client: AsyncClient) -> None:
        resp = await client.get("/api/nylas/webhook", params={"challenge": "test-challenge-123"})
        assert resp.status_code == 200
        assert resp.json() == {"challenge": "test-challenge-123"}

    @pytest.mark.asyncio
    async def test_empty_challenge(self, client: AsyncClient) -> None:
        resp = await client.get("/api/nylas/webhook", params={"challenge": ""})
        assert resp.status_code == 200
        assert resp.json() == {"challenge": ""}

    @pytest.mark.asyncio
    async def test_missing_challenge_defaults_to_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/nylas/webhook")
        assert resp.status_code == 200
        assert resp.json() == {"challenge": ""}


class TestWebhookDeduplication:
    """Test 6: Sending the same message_id twice creates only one event."""

    @pytest.mark.asyncio
    async def test_duplicate_message_id_creates_single_event(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        enrollment = await _enroll_candidate(client, seq_id, "jane@example.com")
        enrollment_id = enrollment["id"]

        await _insert_nylas_account(sf)
        await _seed_outbound_event(sf, enrollment_id, thread_id="thread-dedup")

        payload = _webhook_payload(
            message_id="msg-dedup-001",
            thread_id="thread-dedup",
            sender_email="jane@example.com",
        )

        resp1 = await client.post("/api/nylas/webhook", content=json.dumps(payload))
        assert resp1.status_code == 200

        resp2 = await client.post("/api/nylas/webhook", content=json.dumps(payload))
        assert resp2.status_code == 200

        # Only 1 inbound + 1 seeded outbound = 2 total for this enrollment
        inbound_count = await _count_email_events(sf, enrollment_id, direction="inbound")
        assert inbound_count == 1


class TestUnmatchedWebhook:
    """Test 7: Webhook from unknown sender/thread creates no event."""

    @pytest.mark.asyncio
    async def test_unmatched_sender_no_event(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory
        await _insert_nylas_account(sf)

        payload = _webhook_payload(
            message_id="msg-unknown-001",
            thread_id="thread-unknown-999",
            sender_email="stranger@example.com",
        )

        resp = await client.post("/api/nylas/webhook", content=json.dumps(payload))
        assert resp.status_code == 200

        total = await _count_email_events(sf)
        assert total == 0


class TestOutboundDetection:
    """Test 8: Sender matching Nylas account email creates outbound event, no classification."""

    @pytest.mark.asyncio
    async def test_outbound_event_recorded(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        enrollment = await _enroll_candidate(client, seq_id, "candidate@example.com")
        enrollment_id = enrollment["id"]

        account_email = await _insert_nylas_account(sf)
        await _seed_outbound_event(sf, enrollment_id, thread_id="thread-outbound")

        # Recruiter sends a reply (same thread, sender = recruiter email)
        payload = _webhook_payload(
            message_id="msg-recruiter-reply-001",
            thread_id="thread-outbound",
            sender_email=account_email,
            subject="Re: Hi",
            body="<p>Following up</p>",
            snippet="Following up",
        )

        resp = await client.post("/api/nylas/webhook", content=json.dumps(payload))
        assert resp.status_code == 200

        # Should have 2 outbound events: seed + webhook-recorded
        outbound_count = await _count_email_events(sf, enrollment_id, direction="outbound")
        assert outbound_count == 2

        # No inbound events
        inbound_count = await _count_email_events(sf, enrollment_id, direction="inbound")
        assert inbound_count == 0


class TestSenderFallback:
    """Test 9: No thread_id — match by candidate email instead."""

    @pytest.mark.asyncio
    async def test_fallback_match_by_candidate_email(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        await _enroll_candidate(client, seq_id, "fallback@example.com")

        await _insert_nylas_account(sf)

        # Webhook with no thread_id, but sender matches enrolled candidate
        payload = _webhook_payload(
            message_id="msg-fallback-001",
            thread_id=None,
            sender_email="fallback@example.com",
        )
        # Remove thread_id from data since it's None
        payload["data"]["thread_id"] = None

        resp = await client.post("/api/nylas/webhook", content=json.dumps(payload))
        assert resp.status_code == 200

        inbound_count = await _count_email_events(sf, direction="inbound")
        assert inbound_count == 1


class TestMarkRepliedIdempotency:
    """Test 10: Second inbound reply keeps enrollment in 'replied' status."""

    @pytest.mark.asyncio
    async def test_second_reply_stays_replied(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        enrollment = await _enroll_candidate(client, seq_id, "replier@example.com")
        enrollment_id = enrollment["id"]

        await _insert_nylas_account(sf)
        await _seed_outbound_event(sf, enrollment_id, thread_id="thread-reply")

        # First inbound reply
        payload1 = _webhook_payload(
            message_id="msg-reply-001",
            thread_id="thread-reply",
            sender_email="replier@example.com",
        )
        resp1 = await client.post("/api/nylas/webhook", content=json.dumps(payload1))
        assert resp1.status_code == 200

        # Simulate what the Celery task would do: mark enrollment as replied
        async with sf() as db:
            await db.execute(
                text("UPDATE enrollments SET status = 'replied' WHERE id = :id"),
                {"id": enrollment_id},
            )
            await db.commit()

        status_after_first = await _get_enrollment_status(sf, enrollment_id)
        assert status_after_first == "replied"

        # Second inbound reply (different message_id)
        payload2 = _webhook_payload(
            message_id="msg-reply-002",
            thread_id="thread-reply",
            sender_email="replier@example.com",
        )
        resp2 = await client.post("/api/nylas/webhook", content=json.dumps(payload2))
        assert resp2.status_code == 200

        # Status should still be "replied"
        status_after_second = await _get_enrollment_status(sf, enrollment_id)
        assert status_after_second == "replied"

        # Two inbound events recorded
        inbound_count = await _count_email_events(sf, enrollment_id, direction="inbound")
        assert inbound_count == 2


class TestMalformedWebhook:
    """Test 20: Invalid/incomplete payloads return 200 (no Nylas retry)."""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_200(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/nylas/webhook",
            content=b"not-json{{{",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_missing_fields_returns_200(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory
        await _insert_nylas_account(sf)

        # Payload with no data.id, no from, no thread_id
        resp = await client.post(
            "/api/nylas/webhook",
            content=json.dumps({"data": {}}),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # No events created
        total = await _count_email_events(sf)
        assert total == 0

    @pytest.mark.asyncio
    async def test_empty_body_returns_200(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/nylas/webhook",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
