from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.enrollment import Enrollment
from app.models.enums import EmailDirection
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.referral_repo import ReferralRepository


async def _create_active_sequence(client: AsyncClient, name: str = "Seq") -> str:
    r = await client.post("/api/sequences", json={
        "name": name,
        "steps": [{"subject": "Outreach", "body_html": "<p>Hello</p>", "delay": 0}],
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
        "candidates": [{"email": email, "first_name": "Jane", "last_name": "Doe",
                        "company": "Acme", "title": "Engineer"}],
    })
    assert r.status_code == 201
    r2 = await client.get(f"/api/sequences/{seq_id}/enrollments")
    assert r2.status_code == 200
    items = r2.json()["items"]
    return next(i["id"] for i in items if i["candidate_email"].lower() == email.lower())


class TestEnrollmentTimelineAPI:
    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_422(self, client: AsyncClient) -> None:
        """Non-UUID path param is rejected by FastAPI validation."""
        r = await client.get("/api/enrollments/not-a-uuid/timeline")
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_nonexistent_enrollment_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Valid UUID that doesn't exist returns 404 ENROLLMENT_NOT_FOUND."""
        fake_id = "00000000-0000-0000-0000-000000000099"
        r = await client.get(f"/api/enrollments/{fake_id}/timeline")
        assert r.status_code == 404
        assert r.json()["code"] == "ENROLLMENT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_timeline_response_shape(self, client: AsyncClient) -> None:
        """Enrolled candidate has correct candidate info and enrollment_status in timeline."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "shape@example.com")

        r = await client.get(f"/api/enrollments/{enrollment_id}/timeline")
        assert r.status_code == 200
        data = r.json()

        assert data["candidate"]["email"] == "shape@example.com"
        assert data["candidate"]["name"] == "Jane Doe"
        assert data["candidate"]["company"] == "Acme"
        assert data["candidate"]["title"] == "Engineer"
        assert data["enrollment_status"] == "active"
        assert data["referral"] is None
        assert isinstance(data["timeline"], list)

    @pytest.mark.asyncio
    async def test_timeline_contains_enrolled_transition(
        self, client: AsyncClient
    ) -> None:
        """Timeline always starts with an enrolled transition logged at enrollment time."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "trans@example.com")

        r = await client.get(f"/api/enrollments/{enrollment_id}/timeline")
        assert r.status_code == 200
        timeline = r.json()["timeline"]

        enrolled = next((e for e in timeline if e.get("trigger") == "enrolled"), None)
        assert enrolled is not None
        assert enrolled["type"] == "transition"
        assert enrolled["to_status"] == "active"
        assert enrolled["from_status"] is None

    @pytest.mark.asyncio
    async def test_timeline_includes_seeded_email_events(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """Outbound and inbound email events appear in the timeline in chronological order."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "events@example.com")

        event_repo = EmailEventRepository(db)
        outbound = await event_repo.create(
            enrollment_id=UUID(enrollment_id),
            direction=EmailDirection.OUTBOUND,
            subject="Step 1: Opportunity",
            step_index=0,
        )
        inbound = await event_repo.create(
            enrollment_id=UUID(enrollment_id),
            direction=EmailDirection.INBOUND,
            body_text="I'm interested!",
        )
        inbound.sentiment = "interested"
        await db.commit()

        r = await client.get(f"/api/enrollments/{enrollment_id}/timeline")
        assert r.status_code == 200
        timeline = r.json()["timeline"]

        email_entries = [e for e in timeline if e["type"] == "email"]
        assert len(email_entries) == 2

        directions = [e["direction"] for e in email_entries]
        assert "outbound" in directions
        assert "inbound" in directions

        inbound_entry = next(e for e in email_entries if e["direction"] == "inbound")
        assert inbound_entry["sentiment"] == "interested"

        outbound_entry = next(e for e in email_entries if e["direction"] == "outbound")
        assert outbound_entry["subject"] == "Step 1: Opportunity"
        assert outbound_entry["step_index"] == 0

        # Chronological order: outbound (created first) before inbound
        outbound_idx = timeline.index(outbound_entry)
        inbound_idx = timeline.index(inbound_entry)
        assert outbound_idx < inbound_idx

    @pytest.mark.asyncio
    async def test_timeline_referral_field_populated_for_referred_candidate(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """Timeline referral field is populated when the candidate was referred by someone."""
        # Referrer: enrolled in a sequence
        seq_id = await _create_active_sequence(client)
        referrer_enrollment_id = await _enroll_one(
            client, seq_id, "referrer@example.com"
        )

        referrer_result = await db.execute(
            select(Enrollment).where(Enrollment.id == UUID(referrer_enrollment_id))
        )
        referrer_enrollment = referrer_result.scalar_one()

        # Referred: enrolled separately in the same sequence
        referred_enrollment_id = await _enroll_one(
            client, seq_id, "referred@example.com"
        )
        referred_result = await db.execute(
            select(Enrollment).where(Enrollment.id == UUID(referred_enrollment_id))
        )
        referred_enrollment = referred_result.scalar_one()

        # Create a referral record linking referrer → referred via a source event
        event_repo = EmailEventRepository(db)
        source_event = await event_repo.create(
            enrollment_id=UUID(referrer_enrollment_id),
            direction=EmailDirection.INBOUND,
            body_text="Talk to my colleague at referred@example.com",
        )
        referral_repo = ReferralRepository(db)
        await referral_repo.create(
            referrer_candidate_id=referrer_enrollment.candidate_id,
            referred_candidate_id=referred_enrollment.candidate_id,
            source_email_event_id=source_event.id,
        )
        await db.commit()

        # Referred candidate's timeline should show the referral info
        r = await client.get(f"/api/enrollments/{referred_enrollment_id}/timeline")
        assert r.status_code == 200
        data = r.json()

        assert data["referral"] is not None
        assert data["referral"]["referrer_email"] == "referrer@example.com"

    @pytest.mark.asyncio
    async def test_timeline_referral_null_for_direct_candidate(
        self, client: AsyncClient
    ) -> None:
        """referral field is null for candidates who were not referred by anyone."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "direct@example.com")

        r = await client.get(f"/api/enrollments/{enrollment_id}/timeline")
        assert r.status_code == 200
        assert r.json()["referral"] is None
