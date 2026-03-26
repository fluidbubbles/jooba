from app.integrations.classifier import OpenAIClassifier, get_classifier
from app.models.enums import Sentiment


class TestGetClassifierFactory:
    def test_returns_openai_classifier(self):
        assert isinstance(get_classifier(), OpenAIClassifier)


class TestSentimentEnum:
    def test_all_four_sentiments_exist(self):
        assert Sentiment.INTERESTED.value == "interested"
        assert Sentiment.NOT_INTERESTED.value == "not_interested"
        assert Sentiment.REFERRAL.value == "referral"
        assert Sentiment.NEUTRAL.value == "neutral"

    def test_enum_has_exactly_four_members(self):
        assert len(Sentiment) == 4
