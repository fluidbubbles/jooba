import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import config
from app.models.enums import VALID_TRANSITIONS, EnrollmentStatus, SequenceStatus
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


def _claimed_active_enrollment_mock(
    *,
    enrollment_id: uuid.UUID | None = None,
) -> MagicMock:
    """ACTIVE enrollment with next_send_at=None (claimed / ready to send)."""
    eid = enrollment_id or uuid.uuid4()
    mock_enrollment = MagicMock()
    mock_enrollment.id = eid
    mock_enrollment.status = EnrollmentStatus.ACTIVE.value
    mock_enrollment.next_send_at = None
    mock_enrollment.sequence_id = uuid.uuid4()
    mock_enrollment.current_step = 0
    mock_enrollment.candidate_id = uuid.uuid4()
    mock_enrollment.unsubscribe_token = "token"
    return mock_enrollment


class TestAdvanceStepIdempotency:
    """advance_step must be safe to call twice (Celery at-least-once delivery)."""

    @pytest.mark.parametrize(
        "status",
        [
            EnrollmentStatus.REPLIED,
            EnrollmentStatus.COMPLETED,
            EnrollmentStatus.OPTED_OUT,
            EnrollmentStatus.BOUNCED,
            EnrollmentStatus.PAUSED,
        ],
    )
    @pytest.mark.asyncio
    async def test_non_active_enrollment_does_not_send(self, status: EnrollmentStatus):
        """_advance_step returns without sending when enrollment is not ACTIVE."""
        mock_enrollment = MagicMock()
        mock_enrollment.status = status.value

        mock_repo = AsyncMock()
        mock_repo.get_by_id_for_update.return_value = mock_enrollment

        db = AsyncMock()
        service = EnrollmentService(db)
        service._enrollment_repo = mock_repo

        mock_sender = MagicMock()
        await service._advance_step(uuid.uuid4(), sender=mock_sender, grant_id="gid")

        mock_sender.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_but_not_claimed_does_not_send(self):
        enrollment_id = uuid.uuid4()
        mock_enrollment = MagicMock()
        mock_enrollment.status = EnrollmentStatus.ACTIVE.value
        mock_enrollment.next_send_at = datetime.now(timezone.utc)

        mock_repo = AsyncMock()
        mock_repo.get_by_id_for_update.return_value = mock_enrollment

        db = AsyncMock()
        service = EnrollmentService(db)
        service._enrollment_repo = mock_repo

        mock_sender = MagicMock()
        await service._advance_step(enrollment_id, sender=mock_sender, grant_id="gid")

        mock_sender.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_sequence_pauses_claimed_enrollment(self):
        enrollment_id = uuid.uuid4()
        mock_enrollment = _claimed_active_enrollment_mock(enrollment_id=enrollment_id)

        mock_repo = AsyncMock()
        mock_repo.get_by_id_for_update.return_value = mock_enrollment
        mock_sequence_repo = AsyncMock()
        mock_sequence_repo.get_by_id_for_update.return_value = None

        db = AsyncMock()
        service = EnrollmentService(db)
        service._enrollment_repo = mock_repo
        service._sequence_repo = mock_sequence_repo
        service.mark_paused = AsyncMock()

        mock_sender = MagicMock()
        await service._advance_step(enrollment_id, sender=mock_sender, grant_id="gid")

        mock_sender.send.assert_not_called()
        service.mark_paused.assert_awaited_once_with(
            enrollment_id,
            trigger="integrity_sequence_missing",
        )

    @pytest.mark.asyncio
    async def test_inactive_sequence_pauses_claimed_enrollment(self):
        enrollment_id = uuid.uuid4()
        mock_enrollment = _claimed_active_enrollment_mock(enrollment_id=enrollment_id)

        mock_sequence = MagicMock()
        mock_sequence.status = SequenceStatus.PAUSED.value
        mock_sequence.steps = [MagicMock()]

        mock_repo = AsyncMock()
        mock_repo.get_by_id_for_update.return_value = mock_enrollment
        mock_sequence_repo = AsyncMock()
        mock_sequence_repo.get_by_id_for_update.return_value = mock_sequence

        db = AsyncMock()
        service = EnrollmentService(db)
        service._enrollment_repo = mock_repo
        service._sequence_repo = mock_sequence_repo
        service.mark_paused = AsyncMock()

        mock_sender = MagicMock()
        await service._advance_step(enrollment_id, sender=mock_sender, grant_id="gid")

        mock_sender.send.assert_not_called()
        service.mark_paused.assert_awaited_once_with(
            enrollment_id,
            trigger="integrity_sequence_inactive",
        )

    @pytest.mark.asyncio
    async def test_intermediate_step_logs_email_sent_transition(self):
        enrollment_id = uuid.uuid4()
        mock_enrollment = _claimed_active_enrollment_mock(enrollment_id=enrollment_id)

        step_1 = MagicMock()
        step_1.delay_minutes = 0
        step_2 = MagicMock()
        step_2.delay_minutes = 15
        mock_sequence = MagicMock()
        mock_sequence.status = SequenceStatus.ACTIVE.value
        mock_sequence.steps = [step_1, step_2]

        mock_candidate = MagicMock()
        mock_candidate.email = "jane@example.com"
        mock_candidate.first_name = "Jane"
        mock_candidate.last_name = "Doe"
        mock_candidate.company = "Acme"
        mock_candidate.title = "Engineer"

        mock_repo = AsyncMock()
        mock_repo.get_by_id_for_update.return_value = mock_enrollment
        mock_sequence_repo = AsyncMock()
        mock_sequence_repo.get_by_id_for_update.return_value = mock_sequence
        mock_candidate_repo = AsyncMock()
        mock_candidate_repo.get_by_id.return_value = mock_candidate

        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        service = EnrollmentService(db)
        service._enrollment_repo = mock_repo
        service._sequence_repo = mock_sequence_repo
        service._candidate_repo = mock_candidate_repo
        mock_repo.get_latest_outbound_message_id = AsyncMock(return_value=None)

        mock_sender = MagicMock()
        mock_sender.send.return_value = MagicMock(
            message_id="message-1",
            thread_id="thread-1",
        )

        with patch(
            "app.services.enrollment_service.EmailService.compose",
            return_value={
                "to": "jane@example.com",
                "subject": "Subject",
                "body_html": "<p>Body</p>",
            },
        ):
            await service._advance_step(enrollment_id, sender=mock_sender, grant_id="grant")

        assert mock_enrollment.current_step == 1
        assert mock_enrollment.status == EnrollmentStatus.ACTIVE.value
        assert mock_enrollment.next_send_at is not None
        mock_repo.log_transition.assert_awaited_once_with(
            enrollment_id=enrollment_id,
            from_status=EnrollmentStatus.ACTIVE,
            to_status=EnrollmentStatus.ACTIVE,
            trigger="email_sent",
        )


class TestMarkPaused:
    def test_paused_is_valid_transition_from_active(self):
        assert EnrollmentStatus.PAUSED in VALID_TRANSITIONS[EnrollmentStatus.ACTIVE]

    @pytest.mark.asyncio
    async def test_mark_all_active_paused_counts_successes(self):
        first_id = uuid.uuid4()
        second_id = uuid.uuid4()
        db = AsyncMock()
        service = EnrollmentService(db)
        service._enrollment_repo = AsyncMock()
        service._enrollment_repo.list_active_ids = AsyncMock(return_value=[first_id, second_id])
        service.mark_paused = AsyncMock(side_effect=[True, False])

        paused_count = await service.mark_all_active_paused(trigger="provider_auth_revoked")

        assert paused_count == 1
        assert service.mark_paused.await_count == 2
        assert service.mark_paused.await_args_list[0].args == (first_id,)
        assert service.mark_paused.await_args_list[1].args == (second_id,)
        assert service.mark_paused.await_args_list[0].kwargs == {
            "trigger": "provider_auth_revoked"
        }
        assert service.mark_paused.await_args_list[1].kwargs == {
            "trigger": "provider_auth_revoked"
        }


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
