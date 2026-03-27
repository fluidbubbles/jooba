from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.openai_client import OpenAIClient, ReferralExtraction
from app.models.candidate import Candidate
from app.models.enrollment import Enrollment
from app.models.enums import EmailDirection
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.referral_repo import ReferralRepository
from app.services.exceptions import TransientError


def _build_openai_completion_mock(
    mock_openai_cls: MagicMock, content: str | None
) -> None:
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response


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


async def _seed_referral(
    db: AsyncSession,
    enrollment_id: str,
    referred_email: str = "referred@example.com",
    referred_first: str = "Sarah",
    referred_last: str = "Kim",
    referred_company: str = "Uber",
    referred_title: str = "Staff Eng",
) -> tuple[str, str]:
    """Create an inbound email event and a referral record; return (event_id, referred_candidate_id)."""
    enrollment_result = await db.execute(
        select(Enrollment).where(Enrollment.id == UUID(enrollment_id))
    )
    enrollment = enrollment_result.scalar_one()

    event_repo = EmailEventRepository(db)
    event = await event_repo.create(
        enrollment_id=UUID(enrollment_id),
        direction=EmailDirection.INBOUND,
        body_text=f"Talk to {referred_first} at {referred_email}",
    )

    referred = Candidate(
        email=referred_email,
        first_name=referred_first,
        last_name=referred_last,
        company=referred_company,
        title=referred_title,
    )
    db.add(referred)
    await db.flush()

    referral_repo = ReferralRepository(db)
    await referral_repo.create(
        referrer_candidate_id=enrollment.candidate_id,
        referred_candidate_id=referred.id,
        source_email_event_id=event.id,
    )
    await db.commit()
    return str(event.id), str(referred.id)


class TestReferralExtraction:
    def test_extraction_dataclass_fields(self) -> None:
        """ReferralExtraction holds name, email, title, company."""
        extraction = ReferralExtraction(
            name="Sarah Kim",
            email="sarah@uber.com",
            title="Staff Eng",
            company="Uber",
        )
        assert extraction.name == "Sarah Kim"
        assert extraction.email == "sarah@uber.com"
        assert extraction.title == "Staff Eng"
        assert extraction.company == "Uber"

    def test_extraction_allows_none_fields(self) -> None:
        """All fields can be None when extraction fails."""
        extraction = ReferralExtraction(name=None, email=None, title=None, company=None)
        assert extraction.email is None
        assert extraction.name is None
        assert extraction.title is None
        assert extraction.company is None

    @patch("app.integrations.openai_client.OpenAI")
    def test_extract_referral_parses_valid_json(self, mock_openai_cls: MagicMock) -> None:
        """OpenAIClient.extract_referral parses JSON into ReferralExtraction."""
        _build_openai_completion_mock(
            mock_openai_cls,
            '{"name":"Sarah Kim","email":"sarah@uber.com","title":"Staff Eng","company":"Uber"}'
        )

        client = OpenAIClient()
        result = client.extract_referral(
            "Talk to my colleague Sarah Kim at sarah@uber.com"
        )
        assert result.name == "Sarah Kim"
        assert result.email == "sarah@uber.com"
        assert result.title == "Staff Eng"
        assert result.company == "Uber"

    @pytest.mark.parametrize(
        "content",
        ["not valid json", None],
        ids=["malformed_json", "missing_content"],
    )
    def test_extract_referral_raises_on_invalid_or_missing_content(
        self, content: str | None
    ) -> None:
        """Invalid or missing model content raises TransientError."""
        with patch("app.integrations.openai_client.OpenAI") as mock_openai_cls:
            _build_openai_completion_mock(mock_openai_cls, content)
            client = OpenAIClient()
            with pytest.raises(TransientError):
                client.extract_referral("some text")


class TestReferralAPI:
    @pytest.mark.asyncio
    async def test_get_referral_returns_null_for_nonexistent_event(
        self, client: AsyncClient
    ) -> None:
        """GET referral for an unknown event_id returns null, not a 500."""
        fake_id = "00000000-0000-0000-0000-000000000099"
        r = await client.get(f"/api/inbox/replies/{fake_id}/referral")
        assert r.status_code == 200
        assert r.json() is None

    @pytest.mark.asyncio
    async def test_get_referral_returns_null_when_no_referral_record(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """GET referral for a real event with no referral record returns null."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "noreferral@example.com")

        event_repo = EmailEventRepository(db)
        event = await event_repo.create(
            enrollment_id=UUID(enrollment_id),
            direction=EmailDirection.INBOUND,
        )
        await db.commit()

        r = await client.get(f"/api/inbox/replies/{event.id}/referral")
        assert r.status_code == 200
        assert r.json() is None

    @pytest.mark.asyncio
    async def test_get_referral_returns_info_when_referral_exists(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """GET referral for an event with a referral record returns all ReferralInfo fields."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "referrer@example.com")

        event_id, _ = await _seed_referral(
            db,
            enrollment_id,
            referred_email="sarah.kim@uber.com",
            referred_first="Sarah",
            referred_last="Kim",
            referred_company="Uber",
            referred_title="Staff Eng",
        )

        r = await client.get(f"/api/inbox/replies/{event_id}/referral")
        assert r.status_code == 200
        data = r.json()
        assert data is not None
        assert data["email"] == "sarah.kim@uber.com"
        assert data["title"] == "Staff Eng"
        assert data["company"] == "Uber"
        assert data["has_email"] is True
        assert data["referrer_email"] == "referrer@example.com"

    @pytest.mark.asyncio
    async def test_get_referral_placeholder_email_has_email_false(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """Referred candidate with placeholder email returns has_email=false and null email."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "referrer2@example.com")

        enrollment_result = await db.execute(
            select(Enrollment).where(Enrollment.id == UUID(enrollment_id))
        )
        enrollment = enrollment_result.scalar_one()

        event_repo = EmailEventRepository(db)
        event = await event_repo.create(
            enrollment_id=UUID(enrollment_id),
            direction=EmailDirection.INBOUND,
        )

        fake_event_id = event.id
        placeholder = Candidate(
            email=f"referral-{fake_event_id}@placeholder.local",
            first_name="Alex",
        )
        db.add(placeholder)
        await db.flush()

        referral_repo = ReferralRepository(db)
        await referral_repo.create(
            referrer_candidate_id=enrollment.candidate_id,
            referred_candidate_id=placeholder.id,
            source_email_event_id=event.id,
        )
        await db.commit()

        r = await client.get(f"/api/inbox/replies/{event.id}/referral")
        assert r.status_code == 200
        data = r.json()
        assert data is not None
        assert data["has_email"] is False
        assert data["email"] is None

    @pytest.mark.asyncio
    async def test_enroll_referral_returns_400_when_no_referral_exists(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """POST enroll referral with no referral record returns 400 REFERRAL_NO_EMAIL."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "noreferral2@example.com")

        event_repo = EmailEventRepository(db)
        event = await event_repo.create(
            enrollment_id=UUID(enrollment_id),
            direction=EmailDirection.INBOUND,
        )
        await db.commit()

        r = await client.post(
            f"/api/inbox/replies/{event.id}/referral/enroll",
            json={"sequence_id": seq_id},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "REFERRAL_NO_EMAIL"

    @pytest.mark.asyncio
    async def test_enroll_referral_returns_400_for_placeholder_email(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """POST enroll referral with placeholder email (no_email referral) returns 400."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "referrer3@example.com")

        enrollment_result = await db.execute(
            select(Enrollment).where(Enrollment.id == UUID(enrollment_id))
        )
        enrollment = enrollment_result.scalar_one()

        event_repo = EmailEventRepository(db)
        event = await event_repo.create(
            enrollment_id=UUID(enrollment_id),
            direction=EmailDirection.INBOUND,
        )
        placeholder = Candidate(
            email=f"referral-{event.id}@placeholder.local",
            first_name="NoEmail",
        )
        db.add(placeholder)
        await db.flush()

        referral_repo = ReferralRepository(db)
        await referral_repo.create(
            referrer_candidate_id=enrollment.candidate_id,
            referred_candidate_id=placeholder.id,
            source_email_event_id=event.id,
        )
        await db.commit()

        r = await client.post(
            f"/api/inbox/replies/{event.id}/referral/enroll",
            json={"sequence_id": seq_id},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "REFERRAL_NO_EMAIL"

    @pytest.mark.asyncio
    async def test_enroll_referral_into_nonexistent_sequence_returns_404(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """POST enroll referral into unknown sequence_id returns 404 SEQUENCE_NOT_FOUND."""
        seq_id = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, seq_id, "referrer4@example.com")

        event_id, _ = await _seed_referral(
            db, enrollment_id, referred_email="refperson2@example.com"
        )

        fake_seq = "00000000-0000-0000-0000-000000000099"
        r = await client.post(
            f"/api/inbox/replies/{event_id}/referral/enroll",
            json={"sequence_id": fake_seq},
        )
        assert r.status_code == 404
        assert r.json()["code"] == "SEQUENCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_enroll_referral_into_draft_sequence_returns_400(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """POST enroll referral into a draft (non-active) sequence returns 400."""
        active_seq = await _create_active_sequence(client)
        enrollment_id = await _enroll_one(client, active_seq, "referrer5@example.com")

        event_id, _ = await _seed_referral(
            db, enrollment_id, referred_email="refperson3@example.com"
        )

        draft_r = await client.post("/api/sequences", json={
            "name": "Draft Target",
            "steps": [{"subject": "Hi", "body_html": "<p>Hi</p>", "delay": 0}],
        })
        draft_seq = draft_r.json()["id"]

        r = await client.post(
            f"/api/inbox/replies/{event_id}/referral/enroll",
            json={"sequence_id": draft_seq},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "INVALID_SEQUENCE_DATA"

    @pytest.mark.asyncio
    async def test_enroll_referral_happy_path_creates_enrollment(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """POST enroll referral into active sequence returns 201 and creates enrollment."""
        seq_id = await _create_active_sequence(client, name="Referral Target")
        enrollment_id = await _enroll_one(client, seq_id, "referrer6@example.com")

        event_id, _ = await _seed_referral(
            db, enrollment_id, referred_email="enrollme@example.com"
        )

        r = await client.post(
            f"/api/inbox/replies/{event_id}/referral/enroll",
            json={"sequence_id": seq_id},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["enrolled"] == 1
        assert body["skipped"] == 0
        assert body["total"] == 1

    @pytest.mark.asyncio
    async def test_enroll_referral_idempotent_second_call_skips(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """Enrolling the same referred candidate twice skips the duplicate."""
        seq_id = await _create_active_sequence(client, name="Idempotent Seq")
        enrollment_id = await _enroll_one(client, seq_id, "referrer7@example.com")

        event_id, _ = await _seed_referral(
            db, enrollment_id, referred_email="idempotent@example.com"
        )

        await client.post(
            f"/api/inbox/replies/{event_id}/referral/enroll",
            json={"sequence_id": seq_id},
        )
        r2 = await client.post(
            f"/api/inbox/replies/{event_id}/referral/enroll",
            json={"sequence_id": seq_id},
        )
        assert r2.status_code == 201
        assert r2.json()["enrolled"] == 0
        assert r2.json()["skipped"] == 1
