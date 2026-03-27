from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.email_event import EmailEvent
from app.models.enrollment import Enrollment
from app.models.enums import EmailDirection, EnrollmentStatus, Sentiment, SequenceStatus
from app.models.sequence import Sequence, SequenceStep


class AnalyticsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_aggregate_stats(self) -> dict:
        """Global stats for the dashboard top row."""
        candidates_result = await self._db.execute(select(func.count(Candidate.id)))
        total_candidates = candidates_result.scalar_one()

        sent_result = await self._db.execute(
            select(func.count(EmailEvent.id)).where(
                EmailEvent.direction == EmailDirection.OUTBOUND.value
            )
        )
        total_sent = sent_result.scalar_one()

        replies_result = await self._db.execute(
            select(func.count(EmailEvent.id)).where(
                EmailEvent.direction == EmailDirection.INBOUND.value
            )
        )
        total_replies = replies_result.scalar_one()

        reply_rate = (total_replies / total_sent * 100) if total_sent > 0 else 0.0

        interested_result = await self._db.execute(
            select(func.count(EmailEvent.id)).where(
                and_(
                    EmailEvent.direction == EmailDirection.INBOUND.value,
                    EmailEvent.sentiment == Sentiment.INTERESTED.value,
                )
            )
        )
        total_interested = interested_result.scalar_one()

        return {
            "total_candidates": total_candidates,
            "total_sent": total_sent,
            "total_replies": total_replies,
            "reply_rate": round(reply_rate, 1),
            "total_interested": total_interested,
        }

    async def get_sequence_summaries(self) -> list[dict]:
        """Per-sequence funnel stats via batch queries (no N+1 loops)."""
        seq_stmt = (
            select(
                Sequence.id,
                Sequence.name,
                Sequence.status,
                func.count(func.distinct(SequenceStep.id)).label("step_count"),
            )
            .outerjoin(SequenceStep, Sequence.id == SequenceStep.sequence_id)
            .where(
                Sequence.status.in_(
                    (SequenceStatus.ACTIVE.value, SequenceStatus.PAUSED.value)
                )
            )
            .group_by(
                Sequence.id,
                Sequence.name,
                Sequence.status,
                Sequence.updated_at,
            )
            .order_by(Sequence.updated_at.desc())
        )
        seq_result = await self._db.execute(seq_stmt)
        sequences = seq_result.all()
        seq_ids = [row.id for row in sequences]

        if not seq_ids:
            return []

        enroll_stmt = (
            select(
                Enrollment.sequence_id,
                Enrollment.status,
                func.count(Enrollment.id).label("enrollment_n"),
            )
            .where(Enrollment.sequence_id.in_(seq_ids))
            .group_by(Enrollment.sequence_id, Enrollment.status)
        )
        enroll_result = await self._db.execute(enroll_stmt)
        enroll_counts: dict[str, dict[str, int]] = {}
        for row in enroll_result.all():
            sid = str(row.sequence_id)
            bucket = enroll_counts.setdefault(sid, {"total": 0})
            n = int(row.enrollment_n)
            bucket[row.status] = n
            bucket["total"] += n

        email_stmt = (
            select(
                Enrollment.sequence_id,
                EmailEvent.direction,
                EmailEvent.sentiment,
                func.count(EmailEvent.id).label("event_n"),
            )
            .join(Enrollment, EmailEvent.enrollment_id == Enrollment.id)
            .where(Enrollment.sequence_id.in_(seq_ids))
            .group_by(
                Enrollment.sequence_id,
                EmailEvent.direction,
                EmailEvent.sentiment,
            )
        )
        email_result = await self._db.execute(email_stmt)
        sent_counts: dict[str, int] = {}
        sentiment_counts: dict[str, dict[str, int]] = {}
        for row in email_result.all():
            sid = str(row.sequence_id)
            direction = row.direction
            sentiment = row.sentiment
            count = int(row.event_n)
            if direction == EmailDirection.OUTBOUND.value:
                sent_counts[sid] = sent_counts.get(sid, 0) + count
            elif direction == EmailDirection.INBOUND.value and sentiment:
                sentiment_counts.setdefault(sid, {})[sentiment] = count

        last_stmt = (
            select(
                Enrollment.sequence_id,
                func.max(EmailEvent.created_at).label("last_at"),
            )
            .join(Enrollment, EmailEvent.enrollment_id == Enrollment.id)
            .where(Enrollment.sequence_id.in_(seq_ids))
            .group_by(Enrollment.sequence_id)
        )
        last_result = await self._db.execute(last_stmt)
        last_activity: dict[str, str | None] = {}
        for row in last_result.all():
            last_at = row.last_at
            last_activity[str(row.sequence_id)] = (
                last_at.isoformat() if last_at is not None else None
            )

        summaries: list[dict] = []
        for seq in sequences:
            sid = str(seq.id)
            ec = enroll_counts.get(sid, {"total": 0})
            sc = sentiment_counts.get(sid, {})
            summaries.append(
                {
                    "id": sid,
                    "name": seq.name,
                    "status": seq.status,
                    "step_count": int(seq.step_count),
                    "enrolled": ec.get("total", 0),
                    "sent": sent_counts.get(sid, 0),
                    "replied": ec.get(EnrollmentStatus.REPLIED.value, 0),
                    "interested": sc.get(Sentiment.INTERESTED.value, 0),
                    "last_activity": last_activity.get(sid),
                }
            )

        return summaries
