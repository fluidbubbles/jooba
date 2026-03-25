import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.enrollment import Enrollment


class EmailEvent(Base):
    __tablename__ = "email_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    step_index: Mapped[int | None] = mapped_column()
    subject: Mapped[str | None] = mapped_column(String(500))
    body_html: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    sentiment: Mapped[str | None] = mapped_column(String(30))
    sentiment_reasoning: Mapped[str | None] = mapped_column(Text)
    nylas_message_id: Mapped[str | None] = mapped_column(String(255))
    nylas_thread_id: Mapped[str | None] = mapped_column(String(255))
    is_manual_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    enrollment: Mapped["Enrollment"] = relationship(back_populates="email_events")

    __table_args__ = (
        Index("ix_email_events_thread", "nylas_thread_id"),
        Index(
            "ix_email_events_enrollment_direction_sentiment_created",
            "enrollment_id",
            "direction",
            "sentiment",
            "created_at",
        ),
        UniqueConstraint("nylas_message_id", name="uq_email_events_message_id"),
    )
