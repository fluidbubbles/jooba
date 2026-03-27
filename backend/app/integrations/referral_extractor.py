import logging
from abc import ABC, abstractmethod

from app.core.config import settings
from app.integrations.openai_client import OpenAIClient, ReferralExtraction

logger = logging.getLogger(__name__)


class ReferralExtractor(ABC):
    @abstractmethod
    def extract(self, reply_text: str) -> ReferralExtraction:
        ...


class OpenAIReferralExtractor(ReferralExtractor):
    def __init__(self) -> None:
        self.client = OpenAIClient()

    def extract(self, reply_text: str) -> ReferralExtraction:
        return self.client.extract_referral(reply_text)


class MockReferralExtractor(ReferralExtractor):
    """For testing — extracts name/email from simple patterns."""

    def extract(self, reply_text: str) -> ReferralExtraction:
        import re

        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", reply_text)
        return ReferralExtraction(
            name="Referred Person",
            email=email_match.group(0) if email_match else None,
            title=None,
            company=None,
        )


def get_referral_extractor() -> ReferralExtractor:
    if settings.llm_provider == "mock":
        return MockReferralExtractor()
    if settings.llm_provider != "openai":
        logger.error("Unknown llm_provider %r — falling back to OpenAIReferralExtractor", settings.llm_provider)
    return OpenAIReferralExtractor()
