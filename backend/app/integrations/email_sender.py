import logging
import uuid
from abc import ABC, abstractmethod

from app.core.config import settings
from app.integrations.nylas_client import NylasClient, SendResult
from app.services.exceptions import PermanentError, ProviderRateLimited, TransientError

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
    ) -> SendResult:
        try:
            return self.client.send_email(grant_id, to, subject, body_html, reply_to_message_id)
        except ProviderRateLimited:
            raise
        except TransientError:
            raise
        except PermanentError:
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str or "429" in error_str:
                raise ProviderRateLimited() from e
            if "401" in error_str or "403" in error_str or "auth" in error_str:
                raise PermanentError(f"Nylas auth error: {e}") from e
            raise TransientError(f"Nylas send error: {e}") from e


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
    ) -> SendResult:
        self.sent.append({"grant_id": grant_id, "to": to, "subject": subject, "body_html": body_html})
        logger.info("[MockSender] → %s: %s", to, subject)
        return SendResult(
            message_id=f"mock-{uuid.uuid4().hex[:8]}",
            thread_id=f"mock-thread-{uuid.uuid4().hex[:8]}",
        )


def get_email_sender() -> EmailSender:
    if settings.email_provider == "mock":
        return MockSender()
    if settings.email_provider != "nylas":
        logger.warning("Unknown email_provider %r — falling back to NylasSender", settings.email_provider)
    return NylasSender()
