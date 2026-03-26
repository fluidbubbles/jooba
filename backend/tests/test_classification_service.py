# backend/tests/test_classification_service.py
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.integrations.openai_client import ClassificationResult
from app.models.enums import Sentiment
from app.services.classification_service import ClassificationService


def _build_service():
    service = ClassificationService(db=MagicMock())
    service._event_repo = SimpleNamespace(
        find_by_id=AsyncMock(),
        update_sentiment=AsyncMock(),
    )
    return service


class TestClassify:
    @pytest.mark.asyncio
    async def test_happy_path_classifies_and_persists(self):
        service = _build_service()
        event_id = uuid4()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment=None, body_text="I'd love to chat!", body_html=None,
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult("interested", "detected interest")
            mock_get.return_value = mock_classifier

            await service.classify(event_id)

        service._event_repo.update_sentiment.assert_awaited_once_with(
            event_id, "interested", "detected interest",
        )

    @pytest.mark.asyncio
    async def test_idempotency_skips_already_classified(self):
        service = _build_service()
        event_id = uuid4()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment="interested", body_text="test", body_html=None,
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            await service.classify(event_id)
            mock_get.assert_not_called()

        service._event_repo.update_sentiment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nonexistent_event_returns_early(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = None

        await service.classify(uuid4())

        service._event_repo.update_sentiment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_sentiment_defaults_to_neutral(self):
        service = _build_service()
        event_id = uuid4()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment=None, body_text="some text", body_html=None,
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult("excited", "unknown")
            mock_get.return_value = mock_classifier

            await service.classify(event_id)

        service._event_repo.update_sentiment.assert_awaited_once_with(
            event_id, Sentiment.NEUTRAL.value, "unknown",
        )

    @pytest.mark.asyncio
    async def test_body_text_preferred_over_body_html(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment=None, body_text="plain text", body_html="<p>html</p>",
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult("neutral", "test")
            mock_get.return_value = mock_classifier

            await service.classify(uuid4())

            mock_classifier.classify.assert_called_once_with("plain text")

    @pytest.mark.asyncio
    async def test_falls_back_to_body_html_when_no_text(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment=None, body_text=None, body_html="<p>html</p>",
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult("neutral", "test")
            mock_get.return_value = mock_classifier

            await service.classify(uuid4())

            mock_classifier.classify.assert_called_once_with("<p>html</p>")

    @pytest.mark.asyncio
    async def test_empty_body_passes_empty_string(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment=None, body_text=None, body_html=None,
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult("neutral", "test")
            mock_get.return_value = mock_classifier

            await service.classify(uuid4())

            mock_classifier.classify.assert_called_once_with("")
