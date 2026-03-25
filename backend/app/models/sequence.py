import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import SequenceStatus


class Sequence(Base):
    __tablename__ = "sequences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=SequenceStatus.DRAFT.value)
    role_title: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    steps: Mapped[list["SequenceStep"]] = relationship(
        back_populates="sequence", order_by="SequenceStep.step_order"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="sequence")


class SequenceStep(Base):
    __tablename__ = "sequence_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sequence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sequences.id"), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)

    sequence: Mapped["Sequence"] = relationship(back_populates="steps")
