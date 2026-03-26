import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.core.config import settings
from app.models.enums import EnrollmentStatus, SequenceStatus
from app.schemas.enrollment import CandidateInput
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import InvalidSequenceData, SequenceNotFound
from app.utils.unsubscribe import generate_unsubscribe_token, verify_unsubscribe_token


def _sign_payload(payload: str) -> str:
    return hmac.new(
        settings.secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]


class TestUnsubscribeTokens:
    def test_roundtrip(self) -> None:
        cid, sid = uuid4(), uuid4()
        token = generate_unsubscribe_token(cid, sid)
        result = verify_unsubscribe_token(token)
        assert result is not None
        assert result == (cid, sid)

    def test_tampered_token_rejected(self) -> None:
        cid, sid = uuid4(), uuid4()
        token = generate_unsubscribe_token(cid, sid)
        # Flip last character
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        assert verify_unsubscribe_token(tampered) is None

    def test_tampered_candidate_id_rejected(self) -> None:
        cid, sid = uuid4(), uuid4()
        token = generate_unsubscribe_token(cid, sid)
        candidate_str, sequence_str, signature = token.split(":")
        replacement_candidate = str(uuid4())
        assert replacement_candidate != candidate_str
        tampered = f"{replacement_candidate}:{sequence_str}:{signature}"
        assert verify_unsubscribe_token(tampered) is None

    def test_tampered_sequence_id_rejected(self) -> None:
        cid, sid = uuid4(), uuid4()
        token = generate_unsubscribe_token(cid, sid)
        candidate_str, sequence_str, signature = token.split(":")
        replacement_sequence = str(uuid4())
        assert replacement_sequence != sequence_str
        tampered = f"{candidate_str}:{replacement_sequence}:{signature}"
        assert verify_unsubscribe_token(tampered) is None

    @pytest.mark.parametrize("token", ["not-a-token", ""])
    def test_malformed_token_rejected(self, token: str) -> None:
        assert verify_unsubscribe_token(token) is None

    def test_token_with_wrong_uuid_format_rejected(self) -> None:
        payload = "bad:bad"
        token = f"{payload}:{_sign_payload(payload)}"
        assert verify_unsubscribe_token(token) is None

    def test_different_ids_produce_different_tokens(self) -> None:
        cid1, sid1 = uuid4(), uuid4()
        cid2, sid2 = uuid4(), uuid4()
        token1 = generate_unsubscribe_token(cid1, sid1)
        token2 = generate_unsubscribe_token(cid2, sid2)
        assert token1 != token2


def _build_service() -> EnrollmentService:
    service = EnrollmentService(db=MagicMock())
    service._candidate_repo = SimpleNamespace(
        get_or_create=AsyncMock(),
    )
    service._enrollment_repo = SimpleNamespace(
        create_if_not_exists=AsyncMock(),
        log_transition=AsyncMock(),
        list_by_sequence=AsyncMock(),
        count_by_sequence=AsyncMock(),
        get_analytics=AsyncMock(),
    )
    service._sequence_repo = SimpleNamespace(
        get_by_id=AsyncMock(),
    )
    return service


class TestEnrollmentService:
    @pytest.mark.asyncio
    async def test_enroll_candidates_raises_for_missing_sequence(self) -> None:
        service = _build_service()
        service._sequence_repo.get_by_id.return_value = None

        with pytest.raises(SequenceNotFound):
            await service.enroll_candidates(uuid4(), [CandidateInput(email="a@example.com")])

    @pytest.mark.asyncio
    async def test_enroll_candidates_raises_for_non_active_sequence(self) -> None:
        service = _build_service()
        service._sequence_repo.get_by_id.return_value = SimpleNamespace(
            status=SequenceStatus.DRAFT.value
        )

        with pytest.raises(InvalidSequenceData):
            await service.enroll_candidates(uuid4(), [CandidateInput(email="a@example.com")])

    @pytest.mark.asyncio
    async def test_enroll_candidates_creates_and_logs_transition(self) -> None:
        service = _build_service()
        sequence_id = uuid4()
        candidate_id = uuid4()
        enrollment_id = uuid4()

        service._sequence_repo.get_by_id.return_value = SimpleNamespace(
            status=SequenceStatus.ACTIVE.value
        )
        service._candidate_repo.get_or_create.return_value = (
            SimpleNamespace(id=candidate_id),
            True,
        )
        service._enrollment_repo.create_if_not_exists.return_value = (
            SimpleNamespace(id=enrollment_id),
            True,
        )

        result = await service.enroll_candidates(
            sequence_id,
            [CandidateInput(email="jane@example.com")],
        )

        assert result == {"enrolled": 1, "skipped": 0, "total": 1}
        service._enrollment_repo.create_if_not_exists.assert_awaited_once()
        service._enrollment_repo.log_transition.assert_awaited_once_with(
            enrollment_id=enrollment_id,
            from_status=None,
            to_status=EnrollmentStatus.ACTIVE.value,
            trigger="enrolled",
        )

    @pytest.mark.asyncio
    async def test_enroll_candidates_skips_existing_after_deduplication(self) -> None:
        service = _build_service()
        sequence_id = uuid4()
        candidate_id = uuid4()

        service._sequence_repo.get_by_id.return_value = SimpleNamespace(
            status=SequenceStatus.ACTIVE.value
        )
        service._candidate_repo.get_or_create.return_value = (
            SimpleNamespace(id=candidate_id),
            False,
        )
        service._enrollment_repo.create_if_not_exists.return_value = (
            SimpleNamespace(id=uuid4()),
            False,
        )

        result = await service.enroll_candidates(
            sequence_id,
            [
                CandidateInput(email="Jane@Example.com"),
                CandidateInput(email="jane@example.com"),
            ],
        )

        assert result == {"enrolled": 0, "skipped": 1, "total": 2}
        service._candidate_repo.get_or_create.assert_awaited_once()
        service._enrollment_repo.log_transition.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_enrollments_attaches_total_steps(self) -> None:
        service = _build_service()
        sequence_id = uuid4()
        base_item = {
            "id": uuid4(),
            "candidate_name": "Jane Doe",
            "candidate_email": "jane@example.com",
            "current_step": 0,
            "status": EnrollmentStatus.ACTIVE.value,
            "sentiment": None,
            "created_at": "2026-03-26T00:00:00Z",
        }
        service._sequence_repo.get_by_id.return_value = SimpleNamespace(
            steps=[SimpleNamespace(), SimpleNamespace()]
        )
        service._enrollment_repo.list_by_sequence.return_value = [base_item]
        service._enrollment_repo.count_by_sequence.return_value = 1

        items, total = await service.list_enrollments(
            sequence_id,
            EnrollmentStatus.ACTIVE,
            limit=10,
            offset=20,
        )

        assert total == 1
        assert items[0]["total_steps"] == 2
        service._enrollment_repo.list_by_sequence.assert_awaited_once_with(
            sequence_id,
            EnrollmentStatus.ACTIVE,
            10,
            20,
        )
        service._enrollment_repo.count_by_sequence.assert_awaited_once_with(
            sequence_id,
            EnrollmentStatus.ACTIVE,
        )

    @pytest.mark.asyncio
    async def test_list_enrollments_raises_for_missing_sequence(self) -> None:
        service = _build_service()
        service._sequence_repo.get_by_id.return_value = None

        with pytest.raises(SequenceNotFound):
            await service.list_enrollments(uuid4())

    @pytest.mark.asyncio
    async def test_get_analytics_raises_for_missing_sequence(self) -> None:
        service = _build_service()
        service._sequence_repo.get_by_id.return_value = None

        with pytest.raises(SequenceNotFound):
            await service.get_analytics(uuid4())

    @pytest.mark.asyncio
    async def test_get_analytics_delegates_to_repository(self) -> None:
        service = _build_service()
        sequence_id = uuid4()
        expected = {
            "enrolled": 1,
            "sent": 2,
            "replied": 0,
            "interested": 0,
            "not_interested": 0,
            "neutral": 0,
            "referral": 0,
            "bounced": 0,
            "opted_out": 0,
            "completed": 0,
            "paused": 0,
        }
        service._sequence_repo.get_by_id.return_value = SimpleNamespace(steps=[])
        service._enrollment_repo.get_analytics.return_value = expected

        result = await service.get_analytics(sequence_id)

        assert result == expected
        service._enrollment_repo.get_analytics.assert_awaited_once_with(sequence_id)
