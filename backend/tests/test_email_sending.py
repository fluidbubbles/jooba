import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import config
from app.models.enums import VALID_TRANSITIONS, EnrollmentStatus
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import PermanentError
from app.tasks.dispatcher import CeleryDispatcher, SyncDispatcher, get_dispatcher


def _patched_celery_session() -> tuple[MagicMock, AsyncMock]:
    """Return (session_factory, mock_db) for patching scheduler.celery_session."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_db)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    session_factory = MagicMock(return_value=session_cm)
    return session_factory, mock_db


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


class TestTaskDispatcher:
    def test_get_dispatcher_returns_celery_even_when_email_provider_mock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config.settings, "email_provider", "mock")
        assert isinstance(get_dispatcher(), CeleryDispatcher)

    def test_sync_dispatcher_invokes_registered_handler(self) -> None:
        calls: list[object] = []
        dispatcher = SyncDispatcher()
        dispatcher.register("my.task", lambda x: calls.append(x))
        dispatcher.dispatch("my.task", 42, queue="email")
        assert calls == [42]

    def test_send_due_emails_enqueues_send_sequence_email(self) -> None:
        enrollment_id = uuid.uuid4()
        session_factory, _mock_db = _patched_celery_session()

        service_inst = AsyncMock()
        service_inst.claim_due_enrollments_for_sending = AsyncMock(return_value=[enrollment_id])
        dispatcher = MagicMock()

        with (
            patch("app.tasks.scheduler.celery_session", session_factory),
            patch("app.tasks.scheduler.EnrollmentService") as service_cls,
            patch("app.tasks.scheduler.get_dispatcher", return_value=dispatcher),
        ):
            service_cls.return_value = service_inst
            from app.tasks.scheduler import send_due_emails

            send_due_emails()

        dispatcher.dispatch.assert_called_once_with(
            "app.tasks.email_sending.send_sequence_email",
            str(enrollment_id),
            queue="email",
        )

    def test_send_due_emails_requeues_claim_when_dispatch_fails(self) -> None:
        enrollment_id = uuid.uuid4()
        session_factory, _mock_db = _patched_celery_session()

        service_inst = AsyncMock()
        service_inst.claim_due_enrollments_for_sending = AsyncMock(return_value=[enrollment_id])

        dispatcher = MagicMock()
        dispatcher.dispatch.side_effect = RuntimeError("queue unavailable")
        requeue_claim = AsyncMock()

        with (
            patch("app.tasks.scheduler.celery_session", session_factory),
            patch("app.tasks.scheduler.EnrollmentService") as service_cls,
            patch("app.tasks.scheduler.get_dispatcher", return_value=dispatcher),
            patch("app.tasks.scheduler._requeue_claimed_enrollment", new=requeue_claim),
        ):
            service_cls.return_value = service_inst
            from app.tasks.scheduler import send_due_emails

            send_due_emails()

        dispatcher.dispatch.assert_called_once()
        requeue_claim.assert_awaited_once_with(enrollment_id)
