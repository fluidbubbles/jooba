import logging
from abc import ABC, abstractmethod

from app.core.config import settings
from app.integrations.openai_client import ClassificationResult, OpenAIClient

logger = logging.getLogger(__name__)


class Classifier(ABC):
    @abstractmethod
    def classify(self, reply_text: str) -> ClassificationResult:
        ...


class OpenAIClassifier(Classifier):
    def __init__(self) -> None:
        self.client = OpenAIClient()

    def classify(self, reply_text: str) -> ClassificationResult:
        return self.client.classify_reply(reply_text)


class MockClassifier(Classifier):
    """For testing — returns deterministic results based on keywords."""

    def classify(self, reply_text: str) -> ClassificationResult:
        text = reply_text.lower()
        if any(w in text for w in ["interested", "love to", "let's chat", "schedule", "call"]):
            return ClassificationResult("interested", "Mock: detected interest keywords")
        if any(w in text for w in ["not interested", "no thanks", "happy where", "not looking"]):
            return ClassificationResult("not_interested", "Mock: detected decline keywords")
        if any(w in text for w in ["talk to", "refer", "colleague", "contact"]):
            return ClassificationResult("referral", "Mock: detected referral keywords")
        return ClassificationResult("neutral", "Mock: no strong signal detected")


def get_classifier() -> Classifier:
    if settings.llm_provider == "mock":
        return MockClassifier()
    if settings.llm_provider != "openai":
        logger.warning("Unknown llm_provider %r — falling back to OpenAIClassifier", settings.llm_provider)
    return OpenAIClassifier()
