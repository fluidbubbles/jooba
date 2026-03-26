from unittest.mock import MagicMock, patch

import pytest
from app.integrations.openai_client import OpenAIClient, ReferralExtraction


def _build_openai_completion_mock(
    mock_openai_cls: MagicMock, content: str | None
) -> None:
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response


class TestReferralExtraction:
    def test_extraction_dataclass_fields(self) -> None:
        """ReferralExtraction holds name, email, title, company."""
        extraction = ReferralExtraction(
            name="Sarah Kim",
            email="sarah@uber.com",
            title="Staff Eng",
            company="Uber",
        )
        assert extraction.name == "Sarah Kim"
        assert extraction.email == "sarah@uber.com"
        assert extraction.title == "Staff Eng"
        assert extraction.company == "Uber"

    def test_extraction_allows_none_fields(self) -> None:
        """All fields can be None when extraction fails."""
        extraction = ReferralExtraction(name=None, email=None, title=None, company=None)
        assert extraction.email is None
        assert extraction.name is None
        assert extraction.title is None
        assert extraction.company is None

    @patch("app.integrations.openai_client.OpenAI")
    def test_extract_referral_parses_valid_json(self, mock_openai_cls: MagicMock) -> None:
        """OpenAIClient.extract_referral parses JSON into ReferralExtraction."""
        _build_openai_completion_mock(
            mock_openai_cls,
            '{"name":"Sarah Kim","email":"sarah@uber.com","title":"Staff Eng","company":"Uber"}'
        )

        client = OpenAIClient()
        result = client.extract_referral(
            "Talk to my colleague Sarah Kim at sarah@uber.com"
        )
        assert result.name == "Sarah Kim"
        assert result.email == "sarah@uber.com"
        assert result.title == "Staff Eng"
        assert result.company == "Uber"

    @pytest.mark.parametrize(
        "content",
        ["not valid json", None],
        ids=["malformed_json", "missing_content"],
    )
    def test_extract_referral_returns_none_for_invalid_or_missing_content(
        self, content: str | None
    ) -> None:
        """Invalid or missing model content returns all-None extraction."""
        with patch("app.integrations.openai_client.OpenAI") as mock_openai_cls:
            _build_openai_completion_mock(mock_openai_cls, content)
            client = OpenAIClient()
            result = client.extract_referral("some text")

        assert result.name is None
        assert result.email is None
        assert result.title is None
        assert result.company is None
