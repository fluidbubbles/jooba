from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EmailDirection
from app.repositories.email_event_repo import EmailEventRepository


async def _create_active_sequence(client: AsyncClient, name: str = "Seq") -> str:
    r = await client.post("/api/sequences", json={
        "name": name,
        "steps": [{"subject": "Hi", "body_html": "<p>Hello</p>", "delay": 0}],
    })
    assert r.status_code == 201
    seq_id = r.json()["id"]
    r2 = await client.put(f"/api/sequences/{seq_id}/status", json={"status": "active"})
    assert r2.status_code == 200
    return seq_id


async def _enroll_one(
    client: AsyncClient, seq_id: str, email: str = "test@example.com"
) -> str:
    """Enroll one candidate and return the enrollment_id."""
    r = await client.post(f"/api/sequences/{seq_id}/enroll", json={
        "candidates": [{"email": email, "first_name": "Test"}],
    })
    assert r.status_code == 201
    r2 = await client.get(f"/api/sequences/{seq_id}/enrollments")
    assert r2.status_code == 200
    items = r2.json()["items"]
    return next(i["id"] for i in items if i["candidate_email"].lower() == email.lower())


class TestDashboardAPI:
    @pytest.mark.asyncio
    async def test_dashboard_returns_zero_stats_and_expected_shape_when_empty(
        self, client: AsyncClient
    ) -> None:
        """Empty dashboard returns zeroed metrics with expected response types."""
        r = await client.get("/api/analytics/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["total_candidates"], int)
        assert isinstance(data["total_sent"], int)
        assert isinstance(data["total_replies"], int)
        assert isinstance(data["total_interested"], int)
        assert isinstance(data["unreplied_count"], int)
        assert isinstance(data["reply_rate"], float)
        assert isinstance(data["sequences"], list)
        assert data["total_candidates"] == 0
        assert data["total_sent"] == 0
        assert data["total_replies"] == 0
        assert data["total_interested"] == 0
        assert data["unreplied_count"] == 0
        assert data["reply_rate"] == 0
        assert data["sequences"] == []

    @pytest.mark.asyncio
    async def test_draft_sequence_not_shown_in_sequences(
        self, client: AsyncClient
    ) -> None:
        """Draft sequences are excluded from the dashboard sequence list."""
        await client.post("/api/sequences", json={
            "name": "Draft Seq",
            "steps": [{"subject": "Hi", "body_html": "<p>Hi</p>", "delay": 0}],
        })
        r = await client.get("/api/analytics/dashboard")
        assert r.json()["sequences"] == []

    @pytest.mark.asyncio
    async def test_active_sequence_appears_in_sequences(
        self, client: AsyncClient
    ) -> None:
        """Active sequence shows in dashboard with correct name, status, and step_count."""
        seq_id = await _create_active_sequence(client, name="My Sequence")
        r = await client.get("/api/analytics/dashboard")
        data = r.json()
        assert len(data["sequences"]) == 1
        seq = data["sequences"][0]
        assert seq["id"] == seq_id
        assert seq["name"] == "My Sequence"
        assert seq["status"] == "active"
        assert seq["step_count"] == 1
        assert seq["enrolled"] == 0
        assert seq["sent"] == 0

    @pytest.mark.asyncio
    async def test_paused_sequence_appears_in_sequences(
        self, client: AsyncClient
    ) -> None:
        """Paused sequences are included in the dashboard sequence list."""
        seq_id = await _create_active_sequence(client, name="Paused Seq")
        await client.put(f"/api/sequences/{seq_id}/status", json={"status": "paused"})
        r = await client.get("/api/analytics/dashboard")
        seqs = r.json()["sequences"]
        assert len(seqs) == 1
        assert seqs[0]["status"] == "paused"

    @pytest.mark.asyncio
    async def test_total_candidates_counts_enrolled_candidates(
        self, client: AsyncClient
    ) -> None:
        """total_candidates reflects all enrolled candidates across sequences."""
        seq_id = await _create_active_sequence(client)
        await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [{"email": "a@example.com"}, {"email": "b@example.com"}],
        })
        r = await client.get("/api/analytics/dashboard")
        assert r.json()["total_candidates"] == 2

    @pytest.mark.asyncio
    async def test_sequence_summary_enrolled_count(
        self, client: AsyncClient
    ) -> None:
        """Per-sequence enrolled count in summaries matches actual enrollments."""
        seq_id = await _create_active_sequence(client, name="Funnel Test")
        await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [
                {"email": "x@example.com"},
                {"email": "y@example.com"},
                {"email": "z@example.com"},
            ],
        })
        r = await client.get("/api/analytics/dashboard")
        seq = next(s for s in r.json()["sequences"] if s["id"] == seq_id)
        assert seq["enrolled"] == 3
        assert seq["sent"] == 0
        assert seq["replied"] == 0
        assert seq["interested"] == 0

    @pytest.mark.asyncio
    async def test_email_events_update_sent_replies_and_interested(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """total_sent, total_replies, total_interested, and reply_rate reflect email events."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "tester@example.com")

        event_repo = EmailEventRepository(db)
        await event_repo.create(
            enrollment_id=UUID(enrollment_id),
            direction=EmailDirection.OUTBOUND,
        )
        inbound = await event_repo.create(
            enrollment_id=UUID(enrollment_id),
            direction=EmailDirection.INBOUND,
        )
        inbound.sentiment = "interested"
        await db.commit()

        r = await client.get("/api/analytics/dashboard")
        data = r.json()
        assert data["total_sent"] == 1
        assert data["total_replies"] == 1
        assert data["total_interested"] == 1
        assert data["reply_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_sequence_summary_sent_and_interested_counts(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """Per-sequence sent and interested counts in summaries reflect email events."""
        seq_id = await _create_active_sequence(client, name="Summary Test")
        enrollment_id = await _enroll_one(client, seq_id, "count@example.com")

        event_repo = EmailEventRepository(db)
        await event_repo.create(
            enrollment_id=UUID(enrollment_id),
            direction=EmailDirection.OUTBOUND,
        )
        inbound = await event_repo.create(
            enrollment_id=UUID(enrollment_id),
            direction=EmailDirection.INBOUND,
        )
        inbound.sentiment = "interested"
        await db.commit()

        r = await client.get("/api/analytics/dashboard")
        seq = next(s for s in r.json()["sequences"] if s["id"] == seq_id)
        assert seq["sent"] == 1
        assert seq["interested"] == 1

    @pytest.mark.asyncio
    async def test_reply_rate_zero_when_no_sent(self, client: AsyncClient) -> None:
        """reply_rate is 0.0 with no outbound emails — no division-by-zero error."""
        r = await client.get("/api/analytics/dashboard")
        assert r.json()["reply_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_multiple_sequences_each_show_independent_counts(
        self, client: AsyncClient
    ) -> None:
        """Two sequences each have their own enrollment counts in summaries."""
        seq1 = await _create_active_sequence(client, name="Seq One")
        seq2 = await _create_active_sequence(client, name="Seq Two")
        await client.post(f"/api/sequences/{seq1}/enroll", json={
            "candidates": [{"email": "p1@example.com"}, {"email": "p2@example.com"}],
        })
        await client.post(f"/api/sequences/{seq2}/enroll", json={
            "candidates": [{"email": "p3@example.com"}],
        })
        r = await client.get("/api/analytics/dashboard")
        seqs = {s["id"]: s for s in r.json()["sequences"]}
        assert seqs[seq1]["enrolled"] == 2
        assert seqs[seq2]["enrolled"] == 1
        assert r.json()["total_candidates"] == 3
