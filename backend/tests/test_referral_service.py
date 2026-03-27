"""Unit tests for ReferralService.process_referral business logic."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.integrations.openai_client import ReferralExtraction
from app.services.exceptions import CandidateNotFound, EmailEventNotFound, EnrollmentNotFound
from app.services.referral_service import ReferralService


def _build_service():
    """Build a ReferralService with mocked dependencies."""
    service = ReferralService.__new__(ReferralService)
    service._db = MagicMock()
    service._event_repo = SimpleNamespace(
        find_by_id_for_update=AsyncMock(),
        find_by_id=AsyncMock(),
    )
    service._candidate_repo = SimpleNamespace(
        get_by_id=AsyncMock(),
        get_or_create=AsyncMock(),
    )
    service._referral_repo = SimpleNamespace(
        get_by_email_event=AsyncMock(return_value=None),
        create=AsyncMock(),
    )
    service._enrollment_repo = SimpleNamespace(
        get_by_id=AsyncMock(),
        create_if_not_exists=AsyncMock(return_value=(SimpleNamespace(id=uuid4()), False)),
        log_transition=AsyncMock(),
        get_by_candidate_and_sequence=AsyncMock(return_value=None),
    )
    service._sequence_repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=None),
        get_by_id=AsyncMock(),
    )
    service._extractor = MagicMock()
    return service


def _make_event(enrollment_id=None):
    return SimpleNamespace(
        id=uuid4(),
        enrollment_id=enrollment_id or uuid4(),
        body_html="<p>Talk to Sarah at sarah@uber.com</p>",
        body_text="Talk to Sarah at sarah@uber.com",
    )


def _make_candidate(candidate_id=None, email="referrer@example.com"):
    return SimpleNamespace(id=candidate_id or uuid4(), email=email)


class TestProcessReferral:
    @pytest.mark.asyncio
    async def test_raises_when_event_missing(self) -> None:
        service = _build_service()
        service._event_repo.find_by_id_for_update.return_value = None
        with pytest.raises(EmailEventNotFound):
            await service.process_referral(uuid4())

    @pytest.mark.asyncio
    async def test_idempotent_skips_existing_referral(self) -> None:
        service = _build_service()
        service._event_repo.find_by_id_for_update.return_value = _make_event()
        service._referral_repo.get_by_email_event.return_value = SimpleNamespace(id=uuid4())

        await service.process_referral(uuid4())

        service._extractor.extract.assert_not_called()
        service._referral_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_when_enrollment_missing(self) -> None:
        service = _build_service()
        service._event_repo.find_by_id_for_update.return_value = _make_event()
        service._enrollment_repo.get_by_id.return_value = None

        with pytest.raises(EnrollmentNotFound):
            await service.process_referral(uuid4())

    @pytest.mark.asyncio
    async def test_raises_when_referrer_candidate_missing(self) -> None:
        service = _build_service()
        event = _make_event()
        service._event_repo.find_by_id_for_update.return_value = event
        service._enrollment_repo.get_by_id.return_value = SimpleNamespace(
            candidate_id=uuid4()
        )
        service._candidate_repo.get_by_id.return_value = None

        with pytest.raises(CandidateNotFound):
            await service.process_referral(uuid4())

    @pytest.mark.asyncio
    async def test_skips_when_extraction_yields_nothing(self) -> None:
        service = _build_service()
        event = _make_event()
        service._event_repo.find_by_id_for_update.return_value = event
        service._enrollment_repo.get_by_id.return_value = SimpleNamespace(
            candidate_id=uuid4()
        )
        service._candidate_repo.get_by_id.return_value = _make_candidate()
        service._extractor.extract.return_value = ReferralExtraction(
            name=None, email=None, title=None, company=None,
        )

        await service.process_referral(uuid4())

        service._referral_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_happy_path_with_email_creates_referral(self) -> None:
        service = _build_service()
        event = _make_event()
        referrer = _make_candidate()
        referred = _make_candidate(email="sarah@uber.com")

        service._event_repo.find_by_id_for_update.return_value = event
        service._enrollment_repo.get_by_id.return_value = SimpleNamespace(
            candidate_id=referrer.id,
        )
        service._candidate_repo.get_by_id.return_value = referrer
        service._candidate_repo.get_or_create.return_value = (referred, True)
        service._extractor.extract.return_value = ReferralExtraction(
            name="Sarah Kim", email="sarah@uber.com", title="Staff Eng", company="Uber",
        )

        await service.process_referral(uuid4())

        service._referral_repo.create.assert_called_once()
        call_kwargs = service._referral_repo.create.call_args.kwargs
        assert call_kwargs["referrer_candidate_id"] == referrer.id
        assert call_kwargs["referred_candidate_id"] == referred.id

    @pytest.mark.asyncio
    async def test_missing_email_uses_placeholder(self) -> None:
        service = _build_service()
        event = _make_event()
        referrer = _make_candidate()
        referred = _make_candidate(email=f"referral-{event.id}@placeholder.local")

        service._event_repo.find_by_id_for_update.return_value = event
        service._enrollment_repo.get_by_id.return_value = SimpleNamespace(
            candidate_id=referrer.id,
        )
        service._candidate_repo.get_by_id.return_value = referrer
        service._candidate_repo.get_or_create.return_value = (referred, True)
        service._extractor.extract.return_value = ReferralExtraction(
            name="Alex Johnson", email=None, title=None, company=None,
        )

        await service.process_referral(event.id)

        create_call = service._candidate_repo.get_or_create.call_args
        assert create_call.kwargs["email"].endswith("@placeholder.local")
        service._referral_repo.create.assert_called_once()


class TestNonReferralDoesNotDispatch:
    """Verify that non-referral sentiments do NOT dispatch the extraction task."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sentiment", ["interested", "not_interested", "neutral"],
    )
    async def test_non_referral_sentiments_skip_dispatch(self, sentiment: str) -> None:
        from app.integrations.openai_client import ClassificationResult
        from app.services.classification_service import ClassificationService

        service = ClassificationService(db=MagicMock())
        service._event_repo = SimpleNamespace(
            find_by_id=AsyncMock(return_value=SimpleNamespace(
                sentiment=None, body_text="some text", body_html=None,
            )),
            update_sentiment_if_unset=AsyncMock(return_value=True),
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult(sentiment, "test")
            mock_get.return_value = mock_classifier
            with patch("app.services.classification_service.get_dispatcher") as mock_disp:
                mock_dispatcher = MagicMock()
                mock_disp.return_value = mock_dispatcher
                await service.classify(uuid4())

        mock_dispatcher.dispatch.assert_not_called()
