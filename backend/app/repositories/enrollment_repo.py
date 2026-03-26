from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.email_event import EmailEvent
from app.models.enrollment import Enrollment
from app.models.enums import EnrollmentStatus, Sentiment
from app.models.state_transition import StateTransition


class EnrollmentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        candidate_id: UUID,
        sequence_id: UUID,
        unsubscribe_token: str,
        next_send_at: datetime,
    ) -> Enrollment:
        enrollment = Enrollment(
            candidate_id=candidate_id,
            sequence_id=sequence_id,
            status=EnrollmentStatus.ACTIVE.value,
            current_step=0,
            next_send_at=next_send_at,
            unsubscribe_token=unsubscribe_token,
        )
        self._db.add(enrollment)
        await self._db.flush()
        return enrollment

    async def get_by_id(self, enrollment_id: UUID) -> Enrollment | None:
        result = await self._db.execute(
            select(Enrollment).where(Enrollment.id == enrollment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_candidate_and_sequence(
        self, candidate_id: UUID, sequence_id: UUID
    ) -> Enrollment | None:
        result = await self._db.execute(
            select(Enrollment).where(
                and_(
                    Enrollment.candidate_id == candidate_id,
                    Enrollment.sequence_id == sequence_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_sequence(
        self,
        sequence_id: UUID,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Return enrollments for a sequence with candidate info, for the table view."""
        stmt = (
            select(
                Enrollment.id,
                Enrollment.current_step,
                Enrollment.status,
                Enrollment.created_at,
                Candidate.email,
                Candidate.first_name,
                Candidate.last_name,
            )
            .join(Candidate, Enrollment.candidate_id == Candidate.id)
            .where(Enrollment.sequence_id == sequence_id)
        )

        if status_filter and status_filter != "all":
            stmt = stmt.where(Enrollment.status == status_filter)

        stmt = stmt.order_by(Enrollment.created_at.desc()).limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        rows = result.all()

        items = []
        for row in rows:
            sentiment = await self._get_latest_sentiment(row.id)
            name_parts = [row.first_name or "", row.last_name or ""]
            items.append(
                {
                    "id": row.id,
                    "candidate_name": " ".join(p for p in name_parts if p)
                    or row.email.split("@")[0],
                    "candidate_email": row.email,
                    "current_step": row.current_step,
                    "status": row.status,
                    "sentiment": sentiment,
                    "created_at": row.created_at,
                }
            )
        return items

    async def count_by_sequence(
        self, sequence_id: UUID, status_filter: str | None = None
    ) -> int:
        stmt = (
            select(func.count(Enrollment.id))
            .where(Enrollment.sequence_id == sequence_id)
        )
        if status_filter and status_filter != "all":
            stmt = stmt.where(Enrollment.status == status_filter)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def get_analytics(self, sequence_id: UUID) -> dict:
        """Return aggregated analytics for a sequence."""
        # Enrollment status counts
        status_stmt = (
            select(Enrollment.status, func.count(Enrollment.id))
            .where(Enrollment.sequence_id == sequence_id)
            .group_by(Enrollment.status)
        )
        status_result = await self._db.execute(status_stmt)
        status_counts = dict(status_result.all())

        # Total sent emails (outbound events)
        sent_stmt = (
            select(func.count(EmailEvent.id))
            .join(Enrollment, EmailEvent.enrollment_id == Enrollment.id)
            .where(
                and_(
                    Enrollment.sequence_id == sequence_id,
                    EmailEvent.direction == "outbound",
                )
            )
        )
        sent_result = await self._db.execute(sent_stmt)
        sent_count = sent_result.scalar_one()

        # Sentiment counts (from inbound events)
        sentiment_stmt = (
            select(EmailEvent.sentiment, func.count(EmailEvent.id))
            .join(Enrollment, EmailEvent.enrollment_id == Enrollment.id)
            .where(
                and_(
                    Enrollment.sequence_id == sequence_id,
                    EmailEvent.direction == "inbound",
                    EmailEvent.sentiment.is_not(None),
                )
            )
            .group_by(EmailEvent.sentiment)
        )
        sentiment_result = await self._db.execute(sentiment_stmt)
        sentiment_counts = dict(sentiment_result.all())

        total_enrolled = sum(status_counts.values())
        return {
            "enrolled": total_enrolled,
            "sent": sent_count,
            "replied": status_counts.get(EnrollmentStatus.REPLIED.value, 0),
            "interested": sentiment_counts.get(Sentiment.INTERESTED.value, 0),
            "not_interested": sentiment_counts.get(Sentiment.NOT_INTERESTED.value, 0),
            "neutral": sentiment_counts.get(Sentiment.NEUTRAL.value, 0),
            "referral": sentiment_counts.get(Sentiment.REFERRAL.value, 0),
            "bounced": status_counts.get(EnrollmentStatus.BOUNCED.value, 0),
            "opted_out": status_counts.get(EnrollmentStatus.OPTED_OUT.value, 0),
            "completed": status_counts.get(EnrollmentStatus.COMPLETED.value, 0),
            "paused": status_counts.get(EnrollmentStatus.PAUSED.value, 0),
        }

    async def log_transition(
        self,
        enrollment_id: UUID,
        from_status: str | None,
        to_status: str,
        trigger: str,
    ) -> None:
        transition = StateTransition(
            enrollment_id=enrollment_id,
            from_status=from_status,
            to_status=to_status,
            trigger=trigger,
        )
        self._db.add(transition)
        await self._db.flush()

    async def _get_latest_sentiment(self, enrollment_id: UUID) -> str | None:
        result = await self._db.execute(
            select(EmailEvent.sentiment)
            .where(
                and_(
                    EmailEvent.enrollment_id == enrollment_id,
                    EmailEvent.direction == "inbound",
                    EmailEvent.sentiment.is_not(None),
                )
            )
            .order_by(EmailEvent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
