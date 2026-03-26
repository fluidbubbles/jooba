import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.classifier import get_classifier
from app.models.enums import Sentiment
from app.repositories.email_event_repo import EmailEventRepository
from app.tasks.dispatcher import get_dispatcher

logger = logging.getLogger(__name__)


class ClassificationService:
    def __init__(self, db: AsyncSession) -> None:
        self._event_repo = EmailEventRepository(db)

    async def classify(self, email_event_id: UUID) -> None:
        """Classify an inbound email event's sentiment via LLM."""
        event = await self._event_repo.find_by_id(email_event_id)
        if not event:
            logger.warning("classify called for nonexistent event %s", email_event_id)
            return

        if event.sentiment is not None:
            logger.debug("event %s already classified, skipping", email_event_id)
            return

        classifier = get_classifier()
        # Prefer body_html (full body) over body_text (Nylas snippet, often truncated)
        result = classifier.classify(event.body_html or event.body_text or "")

        try:
            validated = Sentiment(result.sentiment)
        except ValueError:
            logger.error("Unknown sentiment %r from classifier, defaulting to neutral", result.sentiment)
            validated = Sentiment.NEUTRAL

        applied = await self._event_repo.update_sentiment_if_unset(
            email_event_id, validated.value, result.reasoning
        )
        if not applied:
            logger.debug(
                "event %s sentiment already persisted by another worker, skipping dispatch",
                email_event_id,
            )
            return

        if validated == Sentiment.REFERRAL:
            get_dispatcher().dispatch(
                "app.tasks.referral.extract_referral",
                str(email_event_id),
                queue="ai",
            )
