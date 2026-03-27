from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
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
        find_recent_inbound=AsyncMock(return_value=None),
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
    async def test_thread_present_without_match_does_not_use_sender_fallback(self):
        service = _build_service()
        candidate = SimpleNamespace(id=uuid4())
        fallback_enrollment = SimpleNamespace(id=uuid4())

        service._event_repo.find_by_message_id.return_value = None
        service._event_repo.find_by_thread_id.return_value = None
        service._candidate_repo.get_by_email.return_value = candidate
        service._enrollment_repo.get_latest_by_candidate.return_value = fallback_enrollment

        await service.process_webhook({
            "message_id": "msg-1",
            "thread_id": "unknown-thread-id",
            "sender_email": "candidate@b.com",
            "subject": "Re: Hi",
            "body_html": "<p>Still interested</p>",
            "body_text": "Still interested",
        })

        service._enrollment_repo.get_latest_by_candidate.assert_not_awaited()
        service._event_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_thread_can_fallback_to_sender_email(self):
        service = _build_service()
        candidate = SimpleNamespace(id=uuid4())
        enrollment = SimpleNamespace(id=uuid4())
        event = SimpleNamespace(id=uuid4())

        service._event_repo.find_by_message_id.return_value = None
        service._candidate_repo.get_by_email.return_value = candidate
        service._enrollment_repo.get_latest_by_candidate.return_value = enrollment
        service._nylas_repo.get_first.return_value = SimpleNamespace(email="recruiter@co.com")
        service._event_repo.create.return_value = event

        await service.process_webhook({
            "message_id": "msg-1",
            "thread_id": None,
            "sender_email": "candidate@b.com",
            "subject": "Re: Hi",
            "body_html": "<p>Yes</p>",
            "body_text": "Yes",
        })

        service._enrollment_repo.get_latest_by_candidate.assert_awaited_once()
        service._event_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_thread_miss_can_match_via_reply_to_message_id(self):
        service = _build_service()
        enrollment = SimpleNamespace(id=uuid4())
        created_event = SimpleNamespace(id=uuid4())
        parent_event = SimpleNamespace(enrollment_id=enrollment.id)

        async def find_by_message_id_side_effect(message_id: str):
            if message_id == "incoming-msg":
                return None
            if message_id == "parent-msg":
                return parent_event
            return None

        service._event_repo.find_by_message_id.side_effect = find_by_message_id_side_effect
        service._event_repo.find_by_thread_id.return_value = None
        service._enrollment_repo.get_by_id.return_value = enrollment
        service._nylas_repo.get_first.return_value = SimpleNamespace(email="recruiter@co.com")
        service._event_repo.create.return_value = created_event

        await service.process_webhook({
            "message_id": "incoming-msg",
            "thread_id": "unknown-thread",
            "reply_to_message_id": "parent-msg",
            "sender_email": "candidate@b.com",
            "subject": "Re: Hi",
            "body_html": "<p>Yep</p>",
            "body_text": "Yep",
        })

        service._event_repo.create.assert_awaited_once()
        service._enrollment_repo.get_latest_by_candidate.assert_not_awaited()

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

    @pytest.mark.asyncio
    async def test_reply_subject_deduplicates_existing_re_prefixes(self):
        service = _build_service()
        event_id = uuid4()
        enrollment_id = uuid4()
        candidate_id = uuid4()

        service._event_repo.find_by_id.return_value = SimpleNamespace(
            enrollment_id=enrollment_id,
            subject="Re: Re: Following up - Jane",
            nylas_message_id="msg-1",
        )
        service._enrollment_repo.get_by_id.return_value = SimpleNamespace(
            id=enrollment_id,
            candidate_id=candidate_id,
            status=EnrollmentStatus.REPLIED.value,
            unsubscribe_token="tok",
        )
        service._candidate_repo.get_by_id.return_value = SimpleNamespace(email="jane@example.com")
        service._nylas_repo.get_first.return_value = SimpleNamespace(grant_id="grant-1")
        service._event_repo.create.return_value = SimpleNamespace(id=uuid4())

        sender = MagicMock()
        sender.send.return_value = SimpleNamespace(message_id="msg-2", thread_id="thread-1")

        with patch("app.services.email_service.get_email_sender", return_value=sender):
            await service.send_manual_reply(event_id, "<p>Hi</p>")

        assert sender.send.call_args.kwargs["subject"] == "Re: Following up - Jane"
        assert service._event_repo.create.call_args.kwargs["subject"] == "Re: Following up - Jane"
