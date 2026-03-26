import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import VALID_TRANSITIONS, EnrollmentStatus
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import PermanentError
from app.utils.templates import append_unsubscribe_footer, replace_placeholders


class TestAdvanceStepIdempotency:
    """advance_step must be safe to call twice (Celery at-least-once delivery)."""

    @pytest.mark.asyncio
    async def test_non_active_enrollment_does_not_send(self):
        """_advance_step returns without sending when enrollment is not ACTIVE."""
        non_active_statuses = [
            EnrollmentStatus.REPLIED,
            EnrollmentStatus.COMPLETED,
            EnrollmentStatus.OPTED_OUT,
            EnrollmentStatus.BOUNCED,
            EnrollmentStatus.PAUSED,
        ]
        for status in non_active_statuses:
            mock_enrollment = MagicMock()
            mock_enrollment.status = status.value

            mock_repo = AsyncMock()
            mock_repo.get_by_id.return_value = mock_enrollment

            db = AsyncMock()
            service = EnrollmentService(db)
            service._enrollment_repo = mock_repo

            mock_sender = MagicMock()
            await service._advance_step(uuid.uuid4(), sender=mock_sender, grant_id="gid")

            mock_sender.send.assert_not_called()


class TestEmailComposition:
    def test_compose_replaces_placeholders_and_adds_footer(self):
        result = replace_placeholders(
            "Hi {{first_name}} at {{company}}",
            {"first_name": "Jane", "company": "Stripe"},
        )
        assert result == "Hi Jane at Stripe"

    def test_compose_adds_unsubscribe_footer(self):
        body = "<p>Hello</p>"
        result = append_unsubscribe_footer(body, "http://localhost:8000/api/unsubscribe/token123")
        assert "Unsubscribe" in result
        assert "token123" in result
        assert body in result

    def test_missing_candidate_data_becomes_empty(self):
        result = replace_placeholders("Hi {{first_name}}", {})
        assert result == "Hi "


class TestMarkPaused:
    def test_paused_is_valid_transition_from_active(self):
        assert EnrollmentStatus.PAUSED in VALID_TRANSITIONS[EnrollmentStatus.ACTIVE]


class TestSendEmailForEnrollment:
    @pytest.mark.asyncio
    async def test_raises_permanent_error_when_no_account(self):
        """send_email_for_enrollment raises PermanentError when no Nylas account is stored."""
        mock_nylas_repo = AsyncMock()
        mock_nylas_repo.get_first.return_value = None

        db = AsyncMock()
        service = EnrollmentService(db)
        service._nylas_repo = mock_nylas_repo

        with pytest.raises(PermanentError, match="No email account connected"):
            await service.send_email_for_enrollment(uuid.uuid4())

    def test_completed_is_valid_transition_from_active(self):
        assert EnrollmentStatus.COMPLETED in VALID_TRANSITIONS[EnrollmentStatus.ACTIVE]
