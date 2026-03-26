from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.models.enums import EmailDirection, EnrollmentStatus
from app.services.email_service import EmailService
from app.services.exceptions import EmailEventNotFound, PermanentError


def _build_service():
    db = MagicMock()
    dispatcher = MagicMock()
    service = EmailService(db=db, dispatcher=dispatcher)
    service._event_repo = SimpleNamespace(
        find_by_id=AsyncMock(),
        find_by_message_id=AsyncMock(),
        find_by_thread_id=AsyncMock(),
        create=AsyncMock(),
    )
    service._enrollment_repo = SimpleNamespace(
        get_by_id=AsyncMock(),
        get_latest_by_candidate=AsyncMock(),
        log_transition=AsyncMock(),
    )
    service._candidate_repo = SimpleNamespace(
        get_by_email=AsyncMock(),
        get_by_id=AsyncMock(),
    )
    service._nylas_repo = SimpleNamespace(
        get_first=AsyncMock(),
    )
    return service


class TestProcessWebhook:
    @pytest.mark.asyncio
    async def test_dedup_skips_existing_message(self):
        service = _build_service()
        service._event_repo.find_by_message_id.return_value = SimpleNamespace(id=uuid4())

        await service.process_webhook({
            "message_id": "msg-1", "thread_id": "t-1",
            "sender_email": "a@b.com", "subject": "", "body_html": "", "body_text": "",
        })

        service._event_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_enrollment_match_skips(self):
        service = _build_service()
        service._event_repo.find_by_message_id.return_value = None
        service._event_repo.find_by_thread_id.return_value = None
        service._candidate_repo.get_by_email.return_value = None

        await service.process_webhook({
            "message_id": "msg-1", "thread_id": "t-1",
            "sender_email": "unknown@b.com", "subject": "", "body_html": "", "body_text": "",
        })

        service._event_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inbound_creates_event_and_dispatches(self):
        service = _build_service()
        enrollment = SimpleNamespace(id=uuid4())
        event = SimpleNamespace(id=uuid4())

        service._event_repo.find_by_message_id.return_value = None
        service._event_repo.find_by_thread_id.return_value = SimpleNamespace(enrollment_id=enrollment.id)
        service._enrollment_repo.get_by_id.return_value = enrollment
        service._nylas_repo.get_first.return_value = SimpleNamespace(email="recruiter@co.com")
        service._event_repo.create.return_value = event

        await service.process_webhook({
            "message_id": "msg-1", "thread_id": "t-1",
            "sender_email": "candidate@b.com", "subject": "Re: Hi",
            "body_html": "<p>Yes!</p>", "body_text": "Yes!",
        })

        service._event_repo.create.assert_awaited_once()
        call_kwargs = service._event_repo.create.call_args[1]
        assert call_kwargs["direction"] == EmailDirection.INBOUND
        assert service._dispatcher.dispatch.call_count == 2

    @pytest.mark.asyncio
    async def test_outbound_records_external_reply(self):
        service = _build_service()
        enrollment = SimpleNamespace(id=uuid4())

        service._event_repo.find_by_message_id.return_value = None
        service._event_repo.find_by_thread_id.return_value = SimpleNamespace(enrollment_id=enrollment.id)
        service._enrollment_repo.get_by_id.return_value = enrollment
        service._nylas_repo.get_first.return_value = SimpleNamespace(email="recruiter@co.com")

        await service.process_webhook({
            "message_id": "msg-1", "thread_id": "t-1",
            "sender_email": "recruiter@co.com", "subject": "Re: Hi",
            "body_html": "", "body_text": "",
        })

        service._event_repo.create.assert_awaited_once()
        call_kwargs = service._event_repo.create.call_args[1]
        assert call_kwargs["direction"] == EmailDirection.OUTBOUND
        service._dispatcher.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_account_returns_early(self):
        service = _build_service()
        enrollment = SimpleNamespace(id=uuid4())

        service._event_repo.find_by_message_id.return_value = None
        service._event_repo.find_by_thread_id.return_value = SimpleNamespace(enrollment_id=enrollment.id)
        service._enrollment_repo.get_by_id.return_value = enrollment
        service._nylas_repo.get_first.return_value = None

        await service.process_webhook({
            "message_id": "msg-1", "thread_id": "t-1",
            "sender_email": "a@b.com", "subject": "", "body_html": "", "body_text": "",
        })

        service._event_repo.create.assert_not_awaited()


class TestSendManualReply:
    @pytest.mark.asyncio
    async def test_event_not_found_raises(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = None

        with pytest.raises(EmailEventNotFound):
            await service.send_manual_reply(uuid4(), "<p>Hi</p>")

    @pytest.mark.asyncio
    async def test_no_account_raises_permanent_error(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            enrollment_id=uuid4(), subject="Hi", nylas_message_id="msg-1",
        )
        service._enrollment_repo.get_by_id.return_value = SimpleNamespace(
            id=uuid4(), candidate_id=uuid4(), status=EnrollmentStatus.REPLIED.value,
            unsubscribe_token="tok",
        )
        service._candidate_repo.get_by_id.return_value = SimpleNamespace(email="a@b.com")
        service._nylas_repo.get_first.return_value = None

        with pytest.raises(PermanentError, match="No email account connected"):
            await service.send_manual_reply(uuid4(), "<p>Hi</p>")
