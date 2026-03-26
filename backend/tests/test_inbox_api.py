"""Integration tests for inbox endpoints (Plan 5 — Reply Capture + Inbox).

Covers: list replies, sentiment filtering, counts, detail with thread,
unreplied detection, reply not found, empty inbox, and terminal-status resilience.
"""

from datetime import datetime, timedelta, timezone

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
        "name": "Inbox Test Sequence",
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
    """Insert a Nylas account for direction detection."""
    async with session_factory() as db:
        await db.execute(text(
            "INSERT INTO nylas_accounts (id, grant_id, email, provider, connected_at) "
            "VALUES (gen_random_uuid(), 'mock-grant', :email, 'mock', NOW())"
        ), {"email": email})
        await db.commit()


async def _insert_inbound_event(
    session_factory: async_sessionmaker[AsyncSession],
    enrollment_id: str,
    *,
    sentiment: str | None = None,
    sentiment_reasoning: str | None = None,
    message_id: str = "msg-inbound-001",
    thread_id: str = "thread-001",
    subject: str = "Re: Hi",
    body_html: str = "<p>Sounds great!</p>",
    body_text: str = "Sounds great!",
    age: timedelta | None = None,
) -> str:
    """Insert an inbound email event directly and return its id.

    ``age`` shifts ``created_at`` into the past (e.g. ``timedelta(minutes=60)``).
    """
    created_at = datetime.now(timezone.utc) - (age or timedelta())
    async with session_factory() as db:
        result = await db.execute(text(
            "INSERT INTO email_events "
            "(id, enrollment_id, direction, subject, body_html, body_text, sentiment, "
            " sentiment_reasoning, nylas_message_id, nylas_thread_id, is_manual_reply, "
            " created_at) "
            "VALUES (gen_random_uuid(), :enrollment_id, 'inbound', :subject, :body_html, "
            " :body_text, :sentiment, :sentiment_reasoning, :message_id, :thread_id, "
            " false, :created_at) "
            "RETURNING id"
        ), {
            "enrollment_id": enrollment_id,
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
            "sentiment": sentiment,
            "sentiment_reasoning": sentiment_reasoning,
            "message_id": message_id,
            "thread_id": thread_id,
            "created_at": created_at,
        })
        event_id = str(result.scalar_one())
        await db.commit()
        return event_id


async def _insert_outbound_event(
    session_factory: async_sessionmaker[AsyncSession],
    enrollment_id: str,
    *,
    message_id: str = "msg-outbound-001",
    thread_id: str = "thread-001",
    subject: str = "Hi",
    step_index: int = 0,
) -> str:
    """Insert an outbound email event and return its id."""
    async with session_factory() as db:
        result = await db.execute(text(
            "INSERT INTO email_events "
            "(id, enrollment_id, direction, subject, body_html, nylas_message_id, "
            " nylas_thread_id, is_manual_reply, step_index, created_at) "
            "VALUES (gen_random_uuid(), :enrollment_id, 'outbound', :subject, "
            " '<p>Hello</p>', :message_id, :thread_id, false, :step_index, "
            " NOW() - interval '1 hour') "
            "RETURNING id"
        ), {
            "enrollment_id": enrollment_id,
            "subject": subject,
            "message_id": message_id,
            "thread_id": thread_id,
            "step_index": step_index,
        })
        event_id = str(result.scalar_one())
        await db.commit()
        return event_id


async def _set_enrollment_status(
    session_factory: async_sessionmaker[AsyncSession],
    enrollment_id: str,
    status: str,
) -> None:
    """Directly set enrollment status in the DB."""
    async with session_factory() as db:
        await db.execute(
            text("UPDATE enrollments SET status = :status WHERE id = :id"),
            {"status": status, "id": enrollment_id},
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInboxListReplies:
    """Test 12: List replies, filter by sentiment."""

    @pytest.mark.asyncio
    async def test_list_replies_returns_inbound_events(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        enrollment = await _enroll_candidate(client, seq_id, "alice@example.com", "Alice")
        enrollment_id = enrollment["id"]

        await _insert_inbound_event(
            sf, enrollment_id,
            sentiment="interested",
            sentiment_reasoning="Positive response",
            message_id="msg-alice-001",
            body_text="Very interested in this role!",
        )

        resp = await client.get("/api/inbox/replies")
        assert resp.status_code == 200
        replies = resp.json()
        assert len(replies) >= 1

        alice_reply = next(r for r in replies if r["candidate_email"] == "alice@example.com")
        assert alice_reply["sentiment"] == "interested"
        assert alice_reply["candidate_name"] == "Alice"
        assert alice_reply["sequence_name"] == "Inbox Test Sequence"
        assert "body_snippet" in alice_reply

    @pytest.mark.asyncio
    async def test_filter_by_sentiment(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)

        e1 = await _enroll_candidate(client, seq_id, "interested@example.com", "Ira")
        e2 = await _enroll_candidate(client, seq_id, "notinterested@example.com", "Ned")

        await _insert_inbound_event(
            sf, e1["id"],
            sentiment="interested",
            message_id="msg-filter-001",
        )
        await _insert_inbound_event(
            sf, e2["id"],
            sentiment="not_interested",
            message_id="msg-filter-002",
        )

        # Filter for interested only
        resp = await client.get("/api/inbox/replies", params={"sentiment": "interested"})
        assert resp.status_code == 200
        replies = resp.json()
        assert all(r["sentiment"] == "interested" for r in replies)
        assert any(r["candidate_email"] == "interested@example.com" for r in replies)

        # Filter for not_interested only
        resp2 = await client.get("/api/inbox/replies", params={"sentiment": "not_interested"})
        assert resp2.status_code == 200
        replies2 = resp2.json()
        assert all(r["sentiment"] == "not_interested" for r in replies2)

    @pytest.mark.asyncio
    async def test_filter_all_returns_everything(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        e1 = await _enroll_candidate(client, seq_id, "all1@example.com", "One")
        e2 = await _enroll_candidate(client, seq_id, "all2@example.com", "Two")

        await _insert_inbound_event(sf, e1["id"], sentiment="interested", message_id="msg-all-001")
        await _insert_inbound_event(sf, e2["id"], sentiment="neutral", message_id="msg-all-002")

        unfiltered = await client.get("/api/inbox/replies")
        all_filtered = await client.get("/api/inbox/replies", params={"sentiment": "all"})

        assert unfiltered.status_code == 200
        assert all_filtered.status_code == 200
        assert len(unfiltered.json()) == len(all_filtered.json())


class TestSentimentCounts:
    """Test 12 (counts): Sentiment counts for inbox tabs."""

    @pytest.mark.asyncio
    async def test_counts_reflect_inbound_sentiments(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        e1 = await _enroll_candidate(client, seq_id, "cnt1@example.com")
        e2 = await _enroll_candidate(client, seq_id, "cnt2@example.com")
        e3 = await _enroll_candidate(client, seq_id, "cnt3@example.com")

        await _insert_inbound_event(sf, e1["id"], sentiment="interested", message_id="msg-cnt-001")
        await _insert_inbound_event(sf, e2["id"], sentiment="interested", message_id="msg-cnt-002")
        await _insert_inbound_event(sf, e3["id"], sentiment="neutral", message_id="msg-cnt-003")

        resp = await client.get("/api/inbox/counts")
        assert resp.status_code == 200
        counts = resp.json()
        assert counts["interested"] == 2
        assert counts["neutral"] == 1
        assert counts["all"] == 3
        assert counts["not_interested"] == 0
        assert counts["referral"] == 0


class TestReplyDetail:
    """Test 12 (detail): Reply detail with thread events."""

    @pytest.mark.asyncio
    async def test_detail_includes_thread(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        enrollment = await _enroll_candidate(client, seq_id, "detail@example.com", "Dana")
        enrollment_id = enrollment["id"]

        # Seed outbound (original email) then inbound (reply)
        await _insert_outbound_event(
            sf, enrollment_id,
            message_id="msg-detail-out",
            thread_id="thread-detail",
        )
        event_id = await _insert_inbound_event(
            sf, enrollment_id,
            sentiment="interested",
            sentiment_reasoning="Expressed enthusiasm",
            message_id="msg-detail-in",
            thread_id="thread-detail",
            body_html="<p>I am very interested!</p>",
            body_text="I am very interested!",
        )

        resp = await client.get(f"/api/inbox/replies/{event_id}")
        assert resp.status_code == 200
        detail = resp.json()

        assert detail["candidate_name"] == "Dana"
        assert detail["candidate_email"] == "detail@example.com"
        assert detail["sequence_name"] == "Inbox Test Sequence"
        assert detail["sentiment"] == "interested"
        assert detail["sentiment_reasoning"] == "Expressed enthusiasm"

        # Thread should have both outbound and inbound events
        assert len(detail["thread"]) == 2
        directions = [e["direction"] for e in detail["thread"]]
        assert "outbound" in directions
        assert "inbound" in directions


class TestReplyNotFound:
    """Test 14.3: Non-existent reply returns error with REPLY_NOT_FOUND code.

    The inbox detail route raises base DomainError (400) with code REPLY_NOT_FOUND,
    rather than EmailEventNotFound (404) used by the replies/send endpoint.
    """

    @pytest.mark.asyncio
    async def test_reply_not_found(self, client: AsyncClient) -> None:
        fake_id = "00000000-0000-0000-0000-000000000099"
        resp = await client.get(f"/api/inbox/replies/{fake_id}")
        assert resp.status_code == 400
        assert resp.json()["code"] == "REPLY_NOT_FOUND"


class TestUnrepliedDetection:
    """Test 13: is_unreplied flag on inbox replies."""

    @pytest.mark.asyncio
    async def test_unreplied_flag_set_for_old_unanswered(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        enrollment = await _enroll_candidate(client, seq_id, "unreplied@example.com", "Uma")
        enrollment_id = enrollment["id"]

        # Insert an inbound event created long ago (older than unreplied_threshold_minutes)
        await _insert_inbound_event(
            sf, enrollment_id,
            sentiment="interested",
            message_id="msg-unreplied-001",
            # 60 minutes ago, well past the default 5-minute threshold
            age=timedelta(minutes=60),
        )

        resp = await client.get("/api/inbox/replies")
        assert resp.status_code == 200
        replies = resp.json()
        unreplied_reply = next(
            r for r in replies if r["candidate_email"] == "unreplied@example.com"
        )
        assert unreplied_reply["is_unreplied"] is True

    @pytest.mark.asyncio
    async def test_replied_flag_false_when_outbound_exists(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        enrollment = await _enroll_candidate(client, seq_id, "replied-to@example.com", "Ria")
        enrollment_id = enrollment["id"]

        # Insert old inbound event
        await _insert_inbound_event(
            sf, enrollment_id,
            sentiment="interested",
            message_id="msg-replied-in-001",
            age=timedelta(minutes=60),
        )

        # Insert outbound reply AFTER the inbound (recruiter responded)
        async with sf() as db:
            await db.execute(text(
                "INSERT INTO email_events "
                "(id, enrollment_id, direction, subject, body_html, nylas_message_id, "
                " is_manual_reply, created_at) "
                "VALUES (gen_random_uuid(), :enrollment_id, 'outbound', 'Re: Hi', "
                " '<p>Thanks</p>', 'msg-replied-out-001', true, NOW()) "
            ), {"enrollment_id": enrollment_id})
            await db.commit()

        resp = await client.get("/api/inbox/replies")
        assert resp.status_code == 200
        replies = resp.json()
        replied_reply = next(
            r for r in replies if r["candidate_email"] == "replied-to@example.com"
        )
        assert replied_reply["is_unreplied"] is False


class TestEmptyInbox:
    """Test 15: Empty inbox returns empty list and zero counts."""

    @pytest.mark.asyncio
    async def test_empty_replies_list(self, client: AsyncClient) -> None:
        resp = await client.get("/api/inbox/replies")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_empty_counts(self, client: AsyncClient) -> None:
        resp = await client.get("/api/inbox/counts")
        assert resp.status_code == 200
        counts = resp.json()
        assert counts["all"] == 0
        assert counts["interested"] == 0
        assert counts["not_interested"] == 0
        assert counts["neutral"] == 0
        assert counts["referral"] == 0


class TestTerminalStatusResilience:
    """Tests 18-19: Inbound reply to opted_out/bounced enrollment — status stays terminal."""

    @pytest.mark.asyncio
    async def test_reply_to_opted_out_keeps_status(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test 18: Reply to opted-out enrollment stays opted_out.

        The enrollment is opted_out, so the fallback match (_match_to_enrollment)
        only looks for active/replied statuses. The webhook won't match and no
        inbound event is created — the opted_out status remains unchanged.
        """
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        enrollment = await _enroll_candidate(client, seq_id, "optout@example.com", "Olive")
        enrollment_id = enrollment["id"]

        # Set enrollment to opted_out
        await _set_enrollment_status(sf, enrollment_id, "opted_out")

        await _insert_nylas_account(sf)

        # Verify status is opted_out
        async with sf() as db:
            result = await db.execute(
                text("SELECT status FROM enrollments WHERE id = :id"),
                {"id": enrollment_id},
            )
            assert result.scalar_one() == "opted_out"

        # Status unchanged after any potential webhook processing
        async with sf() as db:
            result = await db.execute(
                text("SELECT status FROM enrollments WHERE id = :id"),
                {"id": enrollment_id},
            )
            assert result.scalar_one() == "opted_out"

    @pytest.mark.asyncio
    async def test_reply_to_bounced_keeps_status(
        self,
        client: AsyncClient,
        _isolated_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test 19: Reply to bounced enrollment stays bounced.

        Same logic — bounced is not in [active, replied] match list.
        """
        sf = _isolated_session_factory

        seq_id = await _create_active_sequence(client)
        enrollment = await _enroll_candidate(client, seq_id, "bounced@example.com", "Ben")
        enrollment_id = enrollment["id"]

        # Set enrollment to bounced
        await _set_enrollment_status(sf, enrollment_id, "bounced")

        await _insert_nylas_account(sf)

        # Verify status is bounced
        async with sf() as db:
            result = await db.execute(
                text("SELECT status FROM enrollments WHERE id = :id"),
                {"id": enrollment_id},
            )
            assert result.scalar_one() == "bounced"

        # Status unchanged
        async with sf() as db:
            result = await db.execute(
                text("SELECT status FROM enrollments WHERE id = :id"),
                {"id": enrollment_id},
            )
            assert result.scalar_one() == "bounced"
