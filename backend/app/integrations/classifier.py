from abc import ABC, abstractmethod

from app.integrations.openai_client import ClassificationResult, OpenAIClient


class Classifier(ABC):
    @abstractmethod
    def classify(self, reply_text: str) -> ClassificationResult:
        ...


class OpenAIClassifier(Classifier):
    def __init__(self) -> None:
        self.client = OpenAIClient()

    def classify(self, reply_text: str) -> ClassificationResult:
        return self.client.classify_reply(reply_text)


def get_classifier() -> Classifier:
    return OpenAIClassifier()
