import logging
import uuid
from abc import ABC, abstractmethod

from app.core.config import settings
from app.integrations.nylas_client import NylasClient, SendResult

logger = logging.getLogger(__name__)


class EmailSender(ABC):
    @abstractmethod
    def send(
        self,
        grant_id: str,
        to: str,
        subject: str,
        body_html: str,
        reply_to_message_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SendResult:
        ...


class NylasSender(EmailSender):
    def __init__(self) -> None:
        self.client = NylasClient()

    def send(
        self,
        grant_id: str,
        to: str,
        subject: str,
        body_html: str,
        reply_to_message_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SendResult:
        return self.client.send_email(
            grant_id,
            to,
            subject,
            body_html,
            reply_to_message_id,
            idempotency_key,
        )


class MockSender(EmailSender):
    """For testing — logs sends without hitting Nylas."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(
        self,
        grant_id: str,
        to: str,
        subject: str,
        body_html: str,
        reply_to_message_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SendResult:
        self.sent.append(
            {
                "grant_id": grant_id,
                "to": to,
                "subject": subject,
                "body_html": body_html,
                "idempotency_key": idempotency_key,
            }
        )
        logger.info("[MockSender] → %s: %s", to, subject)
        return SendResult(
            message_id=f"mock-{uuid.uuid4().hex[:8]}",
            thread_id=f"mock-thread-{uuid.uuid4().hex[:8]}",
        )


def get_email_sender() -> EmailSender:
    provider = settings.email_provider
    if provider == "mock":
        return MockSender()
    if provider != "nylas":
        logger.warning(
            "Unknown email_provider %r — falling back to NylasSender",
            provider,
        )
    return NylasSender()
