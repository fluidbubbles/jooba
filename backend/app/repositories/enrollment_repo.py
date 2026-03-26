import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.email_event import EmailEvent
from app.models.enrollment import Enrollment
from app.models.enums import EmailDirection, EnrollmentStatus, Sentiment
from app.models.state_transition import StateTransition
from app.utils.formatting import format_candidate_name

logger = logging.getLogger(__name__)


def _latest_sentiment_subquery() -> Any:
    """Correlated subquery returning the most recent inbound sentiment per enrollment."""
    return (
        select(EmailEvent.sentiment)
        .where(
            and_(
                EmailEvent.enrollment_id == Enrollment.id,
                EmailEvent.direction == EmailDirection.INBOUND.value,
                EmailEvent.sentiment.is_not(None),
            )
        )
        .order_by(EmailEvent.created_at.desc())
        .limit(1)
        .correlate(Enrollment)
        .scalar_subquery()
        .label("latest_sentiment")
    )


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

    async def create_if_not_exists(
        self,
        candidate_id: UUID,
        sequence_id: UUID,
        unsubscribe_token: str,
        next_send_at: datetime,
    ) -> tuple[Enrollment, bool]:
        """Create enrollment if absent.

        Returns (enrollment, is_new). If another transaction creates the same
        candidate+sequence row concurrently, returns the existing enrollment.
        """
        existing = await self.get_by_candidate_and_sequence(candidate_id, sequence_id)
        if existing is not None:
            return existing, False

        try:
            async with self._db.begin_nested():
                enrollment = await self.create(
                    candidate_id=candidate_id,
                    sequence_id=sequence_id,
                    unsubscribe_token=unsubscribe_token,
                    next_send_at=next_send_at,
                )
            return enrollment, True
        except IntegrityError:
            existing = await self.get_by_candidate_and_sequence(candidate_id, sequence_id)
            if existing is not None:
                return existing, False
            logger.error(
                "Unexpected IntegrityError in create_if_not_exists "
                "candidate_id=%s sequence_id=%s",
                candidate_id, sequence_id,
            )
            raise

    async def get_by_id(self, enrollment_id: UUID) -> Enrollment | None:
        result = await self._db.execute(
            select(Enrollment).where(Enrollment.id == enrollment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, enrollment_id: UUID) -> Enrollment | None:
        result = await self._db.execute(
            select(Enrollment).where(Enrollment.id == enrollment_id).with_for_update()
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

    async def get_by_candidate_and_sequence_for_update(
        self, candidate_id: UUID, sequence_id: UUID
    ) -> Enrollment | None:
        result = await self._db.execute(
            select(Enrollment)
            .where(
                and_(
                    Enrollment.candidate_id == candidate_id,
                    Enrollment.sequence_id == sequence_id,
                )
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_latest_outbound_message_id(self, enrollment_id: UUID) -> str | None:
        result = await self._db.execute(
            select(EmailEvent.nylas_message_id)
            .where(
                EmailEvent.enrollment_id == enrollment_id,
                EmailEvent.direction == EmailDirection.OUTBOUND.value,
            )
            .order_by(EmailEvent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_by_candidate(
        self,
        candidate_id: UUID,
        statuses: list[EnrollmentStatus],
    ) -> Enrollment | None:
        """Get the most recent enrollment for a candidate in one of the given statuses."""
        result = await self._db.execute(
            select(Enrollment).where(
                and_(
                    Enrollment.candidate_id == candidate_id,
                    Enrollment.status.in_([s.value for s in statuses]),
                )
            ).order_by(Enrollment.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_sequence(
        self,
        sequence_id: UUID,
        status_filter: EnrollmentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return enrollments for a sequence with candidate info, for the table view."""
        sentiment_sq = _latest_sentiment_subquery()

        stmt = (
            select(
                Enrollment.id,
                Enrollment.current_step,
                Enrollment.status,
                Enrollment.created_at,
                Candidate.email,
                Candidate.first_name,
                Candidate.last_name,
                sentiment_sq,
            )
            .join(Candidate, Enrollment.candidate_id == Candidate.id)
            .where(Enrollment.sequence_id == sequence_id)
        )

        if status_filter is not None:
            stmt = stmt.where(Enrollment.status == status_filter.value)

        stmt = (
            stmt.order_by(Enrollment.created_at.desc(), Enrollment.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        rows = result.all()

        return [
            {
                "id": row.id,
                "candidate_name": format_candidate_name(
                    row.first_name, row.last_name, row.email
                ),
                "candidate_email": row.email,
                "current_step": row.current_step,
                "status": row.status,
                "sentiment": row.latest_sentiment,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    async def count_by_sequence(
        self, sequence_id: UUID, status_filter: EnrollmentStatus | None = None
    ) -> int:
        stmt = select(func.count(Enrollment.id)).where(
            Enrollment.sequence_id == sequence_id
        )
        if status_filter is not None:
            stmt = stmt.where(Enrollment.status == status_filter.value)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def list_active_ids(self) -> list[UUID]:
        result = await self._db.execute(
            select(Enrollment.id).where(Enrollment.status == EnrollmentStatus.ACTIVE.value)
        )
        return list(result.scalars().all())

    async def get_analytics(self, sequence_id: UUID) -> dict[str, int]:
        """Return aggregated analytics for a sequence."""
        status_stmt = (
            select(Enrollment.status, func.count(Enrollment.id))
            .where(Enrollment.sequence_id == sequence_id)
            .group_by(Enrollment.status)
        )
        status_result = await self._db.execute(status_stmt)
        status_counts = dict(status_result.all())

        sent_stmt = (
            select(func.count(EmailEvent.id))
            .join(Enrollment, EmailEvent.enrollment_id == Enrollment.id)
            .where(
                and_(
                    Enrollment.sequence_id == sequence_id,
                    EmailEvent.direction == EmailDirection.OUTBOUND.value,
                )
            )
        )
        sent_result = await self._db.execute(sent_stmt)
        sent_count = sent_result.scalar_one()

        sentiment_stmt = (
            select(EmailEvent.sentiment, func.count(EmailEvent.id))
            .join(Enrollment, EmailEvent.enrollment_id == Enrollment.id)
            .where(
                and_(
                    Enrollment.sequence_id == sequence_id,
                    EmailEvent.direction == EmailDirection.INBOUND.value,
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

    async def claim_due_enrollments(self, limit: int = 100) -> list[UUID]:
        """Atomically claim enrollments due for sending.

        Uses FOR UPDATE SKIP LOCKED to prevent overlapping scheduler cycles.
        Sets next_send_at = NULL so the next cycle skips them.
        """
        result = await self._db.execute(
            text("""
                UPDATE enrollments
                SET next_send_at = NULL, updated_at = now()
                WHERE id IN (
                    SELECT id FROM enrollments
                    WHERE status = :status AND next_send_at <= now()
                    FOR UPDATE SKIP LOCKED
                    LIMIT :limit
                )
                RETURNING id
            """),
            {"status": EnrollmentStatus.ACTIVE.value, "limit": limit},
        )
        rows = result.fetchall()
        return [row[0] for row in rows]

    async def requeue_claimed_enrollment(self, enrollment_id: UUID) -> None:
        """Restore immediate eligibility when scheduler dispatch fails."""
        await self._db.execute(
            text("""
                UPDATE enrollments
                SET next_send_at = now(), updated_at = now()
                WHERE id = :enrollment_id
                  AND status = :status
                  AND next_send_at IS NULL
            """),
            {
                "enrollment_id": enrollment_id,
                "status": EnrollmentStatus.ACTIVE.value,
            },
        )

    async def log_transition(
        self,
        enrollment_id: UUID,
        from_status: EnrollmentStatus | None,
        to_status: EnrollmentStatus,
        trigger: str,
    ) -> None:
        transition = StateTransition(
            enrollment_id=enrollment_id,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
            trigger=trigger,
        )
        self._db.add(transition)
        await self._db.flush()
