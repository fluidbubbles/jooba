from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import Sentiment
from app.repositories.analytics_repo import AnalyticsRepository
from app.repositories.email_event_repo import EmailEventRepository
from app.schemas.analytics import DashboardStats, SequenceSummary

_UNREPLIED_SENTIMENTS: list[str] = [
    Sentiment.INTERESTED.value,
    Sentiment.REFERRAL.value,
    Sentiment.NEUTRAL.value,
]


class AnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self._analytics_repo = AnalyticsRepository(db)
        self._email_event_repo = EmailEventRepository(db)

    async def get_dashboard(self) -> DashboardStats:
        stats = await self._analytics_repo.get_aggregate_stats()
        sequence_rows = await self._analytics_repo.get_sequence_summaries()
        unreplied_ids = await self._email_event_repo.get_unreplied_inbound(
            sentiments=_UNREPLIED_SENTIMENTS,
            older_than_minutes=settings.unreplied_threshold_minutes,
        )
        sequences = [SequenceSummary.model_validate(row) for row in sequence_rows]
        return DashboardStats(
            total_candidates=stats["total_candidates"],
            total_sent=stats["total_sent"],
            total_replies=stats["total_replies"],
            reply_rate=stats["reply_rate"],
            total_interested=stats["total_interested"],
            unreplied_count=len(unreplied_ids),
            sequences=sequences,
        )
