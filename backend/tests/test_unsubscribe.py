import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.enums import EnrollmentStatus
from app.services.enrollment_service import EnrollmentService


@pytest.mark.asyncio
async def test_opt_out_returns_false_for_invalid_token() -> None:
    service = EnrollmentService(AsyncMock())
    with patch("app.services.enrollment_service.verify_unsubscribe_token", return_value=None):
        assert await service.opt_out("invalid") is False


@pytest.mark.asyncio
async def test_opt_out_returns_false_when_stored_token_mismatch() -> None:
    enrollment = MagicMock()
    enrollment.unsubscribe_token = "stored-token"
    service = EnrollmentService(AsyncMock())
    service._enrollment_repo = AsyncMock()
    service._enrollment_repo.get_by_candidate_and_sequence_for_update.return_value = enrollment

    with patch(
        "app.services.enrollment_service.verify_unsubscribe_token",
        return_value=(uuid.uuid4(), uuid.uuid4()),
    ):
        assert await service.opt_out("different-token") is False


@pytest.mark.asyncio
async def test_opt_out_is_idempotent_for_replied() -> None:
    enrollment = MagicMock()
    enrollment.status = EnrollmentStatus.REPLIED.value
    enrollment.unsubscribe_token = "token"
    service = EnrollmentService(AsyncMock())
    service._enrollment_repo = AsyncMock()
    service._enrollment_repo.get_by_candidate_and_sequence_for_update.return_value = enrollment

    with patch(
        "app.services.enrollment_service.verify_unsubscribe_token",
        return_value=(uuid.uuid4(), uuid.uuid4()),
    ):
        assert await service.opt_out("token") is True

    service._enrollment_repo.log_transition.assert_not_called()


@pytest.mark.asyncio
async def test_opt_out_transitions_paused_to_opted_out() -> None:
    enrollment_id = uuid.uuid4()
    enrollment = MagicMock()
    enrollment.id = enrollment_id
    enrollment.status = EnrollmentStatus.PAUSED.value
    enrollment.unsubscribe_token = "token"
    enrollment.next_send_at = datetime.now(timezone.utc)
    service = EnrollmentService(AsyncMock())
    service._enrollment_repo = AsyncMock()
    service._enrollment_repo.get_by_candidate_and_sequence_for_update.return_value = enrollment

    with patch(
        "app.services.enrollment_service.verify_unsubscribe_token",
        return_value=(uuid.uuid4(), uuid.uuid4()),
    ):
        assert await service.opt_out("token") is True

    assert enrollment.status == EnrollmentStatus.OPTED_OUT.value
    assert enrollment.next_send_at is None
    service._enrollment_repo.log_transition.assert_awaited_once_with(
        enrollment_id=enrollment_id,
        from_status=EnrollmentStatus.PAUSED,
        to_status=EnrollmentStatus.OPTED_OUT,
        trigger="unsubscribe_clicked",
    )
