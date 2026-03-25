import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import EnrollmentStatus


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    sequence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sequences.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=EnrollmentStatus.ACTIVE.value)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    next_send_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribe_token: Mapped[str | None] = mapped_column(String(255), index=True)
    nudge_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nudge_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    candidate: Mapped["Candidate"] = relationship(back_populates="enrollments")
    sequence: Mapped["Sequence"] = relationship(back_populates="enrollments")
    email_events: Mapped[list["EmailEvent"]] = relationship(back_populates="enrollment")
    state_transitions: Mapped[list["StateTransition"]] = relationship(back_populates="enrollment")

    __table_args__ = (
        Index("ix_enrollments_status_next_send", "status", "next_send_at"),
        UniqueConstraint("candidate_id", "sequence_id", name="uq_enrollment_candidate_sequence"),
    )
