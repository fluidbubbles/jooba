from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.email_event import EmailEvent
from app.models.enrollment import Enrollment
from app.models.enums import EmailDirection
from app.models.sequence import Sequence
from app.utils.email_quotes import strip_email_quotes


class EmailEventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        enrollment_id: UUID,
        direction: EmailDirection,
        subject: str | None = None,
        body_html: str | None = None,
        body_text: str | None = None,
        nylas_message_id: str | None = None,
        nylas_thread_id: str | None = None,
        is_manual_reply: bool = False,
        step_index: int | None = None,
    ) -> EmailEvent:
        event = EmailEvent(
            enrollment_id=enrollment_id,
            direction=direction.value,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            nylas_message_id=nylas_message_id,
            nylas_thread_id=nylas_thread_id,
            is_manual_reply=is_manual_reply,
            step_index=step_index,
        )
        self._db.add(event)
        await self._db.flush()
        return event

    async def find_by_id(self, event_id: UUID) -> EmailEvent | None:
        result = await self._db.execute(
            select(EmailEvent).where(EmailEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def find_by_id_for_update(self, event_id: UUID) -> EmailEvent | None:
        """Load an email event with a FOR UPDATE lock (prevents duplicate referral extraction from concurrent task retries)."""
        result = await self._db.execute(
            select(EmailEvent).where(EmailEvent.id == event_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def find_by_message_id(self, nylas_message_id: str) -> EmailEvent | None:
        """Find an email event by its Nylas message ID."""
        result = await self._db.execute(
            select(EmailEvent).where(EmailEvent.nylas_message_id == nylas_message_id)
        )
        return result.scalar_one_or_none()

    async def find_by_thread_id(self, thread_id: str) -> EmailEvent | None:
        """Find the most recent email event in a Nylas thread."""
        result = await self._db.execute(
            select(EmailEvent)
            .where(EmailEvent.nylas_thread_id == thread_id)
            .order_by(EmailEvent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_sentiment(
        self, event_id: UUID, sentiment: str, reasoning: str
    ) -> None:
        result = await self._db.execute(
            update(EmailEvent)
            .where(EmailEvent.id == event_id)
            .values(sentiment=sentiment, sentiment_reasoning=reasoning)
        )
        if result.rowcount == 0:
            raise ValueError(f"EmailEvent {event_id} not found for sentiment update")
        await self._db.flush()

    async def update_sentiment_if_unset(
        self, event_id: UUID, sentiment: str, reasoning: str
    ) -> bool:
        """Set sentiment only when currently null. Returns True if this call applied the update."""
        result = await self._db.execute(
            update(EmailEvent)
            .where(
                EmailEvent.id == event_id,
                EmailEvent.sentiment.is_(None),
            )
            .values(sentiment=sentiment, sentiment_reasoning=reasoning)
        )
        await self._db.flush()
        return result.rowcount > 0

    async def get_thread(self, enrollment_id: UUID) -> list[EmailEvent]:
        """Get all email events for an enrollment, chronologically."""
        result = await self._db.execute(
            select(EmailEvent)
            .where(EmailEvent.enrollment_id == enrollment_id)
            .order_by(EmailEvent.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    def _latest_inbound_per_enrollment():
        """Subquery: latest inbound event per enrollment (by created_at)."""
        return (
            select(
                EmailEvent.enrollment_id,
                func.max(EmailEvent.created_at).label("latest_ts"),
            )
            .where(EmailEvent.direction == EmailDirection.INBOUND.value)
            .group_by(EmailEvent.enrollment_id)
            .subquery()
        )

    async def get_inbox_replies(
        self,
        sentiment_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get one inbox entry per enrollment, showing the latest inbound reply."""
        latest_sq = self._latest_inbound_per_enrollment()

        stmt = (
            select(
                EmailEvent.id,
                EmailEvent.enrollment_id,
                EmailEvent.body_text,
                EmailEvent.sentiment,
                EmailEvent.sentiment_reasoning,
                EmailEvent.created_at,
                Candidate.first_name,
                Candidate.last_name,
                Candidate.email.label("candidate_email"),
                Sequence.name.label("sequence_name"),
            )
            .join(
                latest_sq,
                and_(
                    EmailEvent.enrollment_id == latest_sq.c.enrollment_id,
                    EmailEvent.created_at == latest_sq.c.latest_ts,
                ),
            )
            .where(EmailEvent.direction == EmailDirection.INBOUND.value)
            .join(Enrollment, EmailEvent.enrollment_id == Enrollment.id)
            .join(Candidate, Enrollment.candidate_id == Candidate.id)
            .join(Sequence, Enrollment.sequence_id == Sequence.id)
        )

        if sentiment_filter and sentiment_filter != "all":
            stmt = stmt.where(EmailEvent.sentiment == sentiment_filter)

        stmt = stmt.order_by(EmailEvent.created_at.desc()).limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        rows = result.all()

        return [
            {
                "id": str(row.id),
                "enrollment_id": str(row.enrollment_id),
                "body_snippet": strip_email_quotes(row.body_text or "")[:120],
                "sentiment": row.sentiment,
                "sentiment_reasoning": row.sentiment_reasoning,
                "created_at": row.created_at,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "candidate_email": row.candidate_email,
                "sequence_name": row.sequence_name,
            }
            for row in rows
        ]

    async def get_sentiment_counts(self) -> dict[str, int]:
        """Get count of conversations (one per enrollment) per sentiment."""
        latest_sq = self._latest_inbound_per_enrollment()

        result = await self._db.execute(
            select(EmailEvent.sentiment, func.count(EmailEvent.id))
            .join(
                latest_sq,
                and_(
                    EmailEvent.enrollment_id == latest_sq.c.enrollment_id,
                    EmailEvent.created_at == latest_sq.c.latest_ts,
                ),
            )
            .where(
                and_(
                    EmailEvent.direction == EmailDirection.INBOUND.value,
                    EmailEvent.sentiment.is_not(None),
                )
            )
            .group_by(EmailEvent.sentiment)
        )
        counts = dict(result.all())
        total = sum(counts.values())
        return {"all": total, **counts}

    async def get_unreplied_inbound(
        self,
        sentiments: list[str],
        older_than_minutes: int,
    ) -> list[UUID]:
        """Find inbound replies the recruiter hasn't responded to yet.

        Query-based, no timers. See Architecture Section 5.7.
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)

        stmt = text("""
            SELECT e.id FROM email_events e
            JOIN enrollments en ON e.enrollment_id = en.id
            WHERE e.direction = 'inbound'
              AND e.sentiment = ANY(:sentiments)
              AND e.created_at < :threshold
              AND NOT EXISTS (
                  SELECT 1 FROM email_events e2
                  WHERE e2.enrollment_id = en.id
                    AND e2.direction = 'outbound'
                    AND e2.created_at > e.created_at
              )
        """)
        result = await self._db.execute(
            stmt, {"sentiments": sentiments, "threshold": threshold}
        )
        return [row[0] for row in result.fetchall()]
