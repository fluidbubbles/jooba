from unittest.mock import patch

import pytest
from app.integrations.classifier import MockClassifier, OpenAIClassifier, get_classifier
from app.integrations.openai_client import ClassificationResult
from app.models.enums import Sentiment


class TestMockClassifier:
    def test_classifies_interested(self):
        c = MockClassifier()
        result = c.classify("I'd love to chat! Are you free Thursday?")
        assert result.sentiment == "interested"

    def test_classifies_not_interested(self):
        c = MockClassifier()
        result = c.classify("Thanks but I'm not interested right now")
        assert result.sentiment == "not_interested"

    def test_classifies_referral(self):
        c = MockClassifier()
        result = c.classify("Not me, but you should talk to my colleague Sarah")
        assert result.sentiment == "referral"

    def test_classifies_neutral(self):
        c = MockClassifier()
        result = c.classify("Can you tell me more about the compensation?")
        assert result.sentiment == "neutral"

    def test_returns_classification_result(self):
        c = MockClassifier()
        result = c.classify("love to chat")
        assert isinstance(result, ClassificationResult)
        assert result.reasoning  # should have a non-empty reasoning string

    def test_not_interested_takes_priority_over_interested(self):
        """'not interested' contains the word 'interested', but not_interested
        keywords are checked first so the decline wins."""
        c = MockClassifier()
        result = c.classify("I'm not interested in this role")
        assert result.sentiment == "not_interested"

    def test_case_insensitive(self):
        c = MockClassifier()
        assert c.classify("NOT INTERESTED").sentiment == "not_interested"
        assert c.classify("LOVE TO chat").sentiment == "interested"
        assert c.classify("Talk to my COLLEAGUE").sentiment == "referral"

    def test_empty_string_is_neutral(self):
        c = MockClassifier()
        assert c.classify("").sentiment == "neutral"

    def test_no_keywords_is_neutral(self):
        c = MockClassifier()
        result = c.classify("Okay, let me think about it.")
        assert result.sentiment == "neutral"


class TestSentimentEnum:
    def test_all_four_sentiments_exist(self):
        assert Sentiment.INTERESTED.value == "interested"
        assert Sentiment.NOT_INTERESTED.value == "not_interested"
        assert Sentiment.REFERRAL.value == "referral"
        assert Sentiment.NEUTRAL.value == "neutral"

    def test_classify_result_matches_enum(self):
        c = MockClassifier()
        for text, expected in [
            ("love to chat", "interested"),
            ("no thanks", "not_interested"),
            ("talk to my colleague", "referral"),
            ("what's the salary?", "neutral"),
        ]:
            result = c.classify(text)
            assert Sentiment(result.sentiment) == Sentiment(expected)

    def test_enum_has_exactly_four_members(self):
        assert len(Sentiment) == 4


class TestGetClassifierFactory:
    @patch("app.integrations.classifier.settings")
    def test_mock_provider_returns_mock_classifier(self, mock_settings):
        mock_settings.llm_provider = "mock"
        assert isinstance(get_classifier(), MockClassifier)

    @patch("app.integrations.classifier.settings")
    def test_openai_provider_returns_openai_classifier(self, mock_settings):
        mock_settings.llm_provider = "openai"
        mock_settings.openai_api_key = "test-key"
        assert isinstance(get_classifier(), OpenAIClassifier)

    @patch("app.integrations.classifier.settings")
    def test_unknown_provider_falls_back_to_openai(self, mock_settings):
        mock_settings.llm_provider = "typo"
        mock_settings.openai_api_key = "test-key"
        result = get_classifier()
        assert isinstance(result, OpenAIClassifier)
