import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.classifier import get_classifier
from app.models.enums import Sentiment
from app.repositories.email_event_repo import EmailEventRepository
from app.tasks.dispatcher import TaskDispatcher, get_dispatcher

logger = logging.getLogger(__name__)


class ClassificationService:
    def __init__(self, db: AsyncSession, dispatcher: TaskDispatcher | None = None):
        self._db = db
        self._event_repo = EmailEventRepository(db)
        self._dispatcher = dispatcher or get_dispatcher()

    async def classify(self, email_event_id: UUID) -> None:
        """Classify an inbound email event's sentiment via LLM."""
        event = await self._event_repo.find_by_id(email_event_id)
        if not event:
            logger.warning("classify called for nonexistent event %s", email_event_id)
            return

        # Idempotency: skip if already classified
        if event.sentiment is not None:
            return

        classifier = get_classifier()
        result = classifier.classify(event.body_text or event.body_html or "")

        # Validate sentiment is a known value
        try:
            validated = Sentiment(result.sentiment)
        except ValueError:
            logger.warning("Unknown sentiment %r from classifier, defaulting to neutral", result.sentiment)
            validated = Sentiment.NEUTRAL

        await self._event_repo.update_sentiment(
            email_event_id, validated.value, result.reasoning
        )

        # Dispatch downstream tasks based on classification
        if validated == Sentiment.REFERRAL:
            self._dispatcher.dispatch(
                "app.tasks.referral.extract_referral",
                str(email_event_id),
                queue="ai",
            )
