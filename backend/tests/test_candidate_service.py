"""Unit tests for CandidateService timeline (mocked repositories)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.candidate_service import CandidateService
from app.services.exceptions import CandidateNotFound, EnrollmentNotFound


def _timeline_service() -> CandidateService:
    svc = CandidateService(db=MagicMock())
    svc._enrollment_repo = SimpleNamespace(
        get_by_id=AsyncMock(),
        list_state_transitions=AsyncMock(),
    )
    svc._candidate_repo = SimpleNamespace(get_by_id=AsyncMock())
    svc._event_repo = SimpleNamespace(get_thread=AsyncMock())
    svc._referral_repo = SimpleNamespace(get_by_referred_candidate=AsyncMock())
    return svc


@pytest.mark.asyncio
async def test_get_timeline_missing_enrollment_raises() -> None:
    service = _timeline_service()
    eid = uuid4()
    service._enrollment_repo.get_by_id.return_value = None

    with pytest.raises(EnrollmentNotFound) as exc_info:
        await service.get_timeline(eid)

    assert exc_info.value.code == "ENROLLMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_timeline_missing_candidate_raises() -> None:
    service = _timeline_service()
    eid, cid = uuid4(), uuid4()
    enrollment = SimpleNamespace(id=eid, candidate_id=cid, status="active")
    service._enrollment_repo.get_by_id.return_value = enrollment
    service._candidate_repo.get_by_id.return_value = None

    with pytest.raises(CandidateNotFound) as exc_info:
        await service.get_timeline(eid)

    assert exc_info.value.code == "CANDIDATE_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_timeline_merges_and_orders_transition_and_email() -> None:
    service = _timeline_service()
    eid, cid = uuid4(), uuid4()
    enrollment = SimpleNamespace(id=eid, candidate_id=cid, status="active")
    candidate = SimpleNamespace(
        id=cid,
        email="c@example.com",
        first_name="Casey",
        last_name=None,
        company=None,
        title=None,
    )
    service._enrollment_repo.get_by_id.return_value = enrollment
    service._candidate_repo.get_by_id.return_value = candidate

    t_morning = datetime(2025, 6, 1, 8, 0, tzinfo=timezone.utc)
    t_noon = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    t_evening = datetime(2025, 6, 1, 18, 0, tzinfo=timezone.utc)

    trans_early = SimpleNamespace(
        created_at=t_morning,
        from_status=None,
        to_status="active",
        trigger="enroll",
    )
    trans_late = SimpleNamespace(
        created_at=t_evening,
        from_status="active",
        to_status="replied",
        trigger="inbound_reply",
    )
    service._enrollment_repo.list_state_transitions.return_value = [
        trans_late,
        trans_early,
    ]

    event = SimpleNamespace(
        created_at=t_noon,
        direction="inbound",
        subject="Re: Hello",
        body_text="Thanks for reaching out",
        body_html=None,
        sentiment="neutral",
        step_index=None,
        is_manual_reply=False,
    )
    service._event_repo.get_thread.return_value = [event]
    service._referral_repo.get_by_referred_candidate.return_value = None

    result = await service.get_timeline(eid)

    assert result["enrollment_status"] == "active"
    assert result["candidate"]["email"] == "c@example.com"
    assert result["referral"] is None

    timeline = result["timeline"]
    assert len(timeline) == 3
    assert timeline[0]["type"] == "transition" and timeline[0]["timestamp"] == t_morning
    assert timeline[1]["type"] == "email" and timeline[1]["timestamp"] == t_noon
    assert timeline[2]["type"] == "transition" and timeline[2]["timestamp"] == t_evening

    email = timeline[1]
    assert email["direction"] == "inbound"
    assert email["subject"] == "Re: Hello"
    assert email["body_snippet"] == "Thanks for reaching out"
    assert email["sentiment"] == "neutral"
    assert email["step_index"] is None
    assert email["is_manual_reply"] is False

    trans = timeline[0]
    assert trans["from_status"] is None
    assert trans["to_status"] == "active"
    assert trans["trigger"] == "enroll"


@pytest.mark.asyncio
async def test_get_timeline_includes_referral_when_present() -> None:
    service = _timeline_service()
    eid, cid, ref_cid = uuid4(), uuid4(), uuid4()
    enrollment = SimpleNamespace(id=eid, candidate_id=cid, status="active")
    candidate = SimpleNamespace(
        id=cid,
        email="referred@example.com",
        first_name="Referred",
        last_name="User",
        company=None,
        title=None,
    )
    referrer = SimpleNamespace(
        id=ref_cid,
        email="referrer@example.com",
        first_name="Pat",
        last_name="Referrer",
        company=None,
        title=None,
    )
    service._enrollment_repo.get_by_id.return_value = enrollment
    service._candidate_repo.get_by_id.side_effect = [candidate, referrer]

    service._enrollment_repo.list_state_transitions.return_value = []
    service._event_repo.get_thread.return_value = []
    service._referral_repo.get_by_referred_candidate.return_value = SimpleNamespace(
        referrer_candidate_id=ref_cid,
    )

    result = await service.get_timeline(eid)

    assert result["referral"] == {
        "referrer_name": "Pat Referrer",
        "referrer_email": "referrer@example.com",
    }
