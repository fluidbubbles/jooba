import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import ColumnElement, delete, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import class_mapper, selectinload
from sqlalchemy.sql.selectable import Subquery

from app.models.email_event import EmailEvent
from app.models.enrollment import Enrollment
from app.models.enums import EnrollmentStatus
from app.models.referral import Referral
from app.models.sequence import Sequence, SequenceStep
from app.models.state_transition import StateTransition


def _count_by_sequence_subquery(
    model: type[Enrollment] | type[SequenceStep],
    *,
    label: str,
    where: ColumnElement[bool] | None = None,
) -> Subquery:
    stmt = select(
        model.sequence_id,
        func.count(model.id).label(label),
    ).group_by(model.sequence_id)
    if where is not None:
        stmt = stmt.where(where)
    return stmt.subquery()


class SequenceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _get_by_id_stmt(self, sequence_id: uuid.UUID, *, for_update: bool = False):
        stmt = (
            select(Sequence)
            .where(Sequence.id == sequence_id)
            .execution_options(populate_existing=True)
            .options(selectinload(Sequence.steps))
        )
        if for_update:
            stmt = stmt.with_for_update()
        return stmt

    async def get_by_id(self, sequence_id: uuid.UUID) -> Sequence | None:
        stmt = self._get_by_id_stmt(sequence_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Sequence | None:
        stmt = (
            select(Sequence)
            .where(Sequence.name == name)
            .options(selectinload(Sequence.steps))
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, sequence_id: uuid.UUID) -> Sequence | None:
        stmt = self._get_by_id_stmt(sequence_id, for_update=True)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def _list_base_stmt(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
    ):
        step_sq = _count_by_sequence_subquery(SequenceStep, label="step_count")
        enrolled_sq = _count_by_sequence_subquery(Enrollment, label="enrolled_count")
        replied_sq = _count_by_sequence_subquery(
            Enrollment,
            label="replied_count",
            where=Enrollment.status == EnrollmentStatus.REPLIED.value,
        )
        stmt = (
            select(
                Sequence.id,
                Sequence.name,
                Sequence.status,
                Sequence.created_at,
                func.coalesce(step_sq.c.step_count, 0).label("step_count"),
                func.coalesce(enrolled_sq.c.enrolled_count, 0).label("enrolled_count"),
                func.coalesce(replied_sq.c.replied_count, 0).label("replied_count"),
            )
            .outerjoin(step_sq, Sequence.id == step_sq.c.sequence_id)
            .outerjoin(enrolled_sq, Sequence.id == enrolled_sq.c.sequence_id)
            .outerjoin(replied_sq, Sequence.id == replied_sq.c.sequence_id)
        )
        if q:
            stmt = stmt.where(Sequence.name.ilike(f"%{q}%"))
        if status:
            stmt = stmt.where(Sequence.status == status)
        return stmt

    async def list_paginated(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        sort: str = "created",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        base = self._list_base_stmt(q=q, status=status)
        count_result = await self._db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()

        if sort == "enrolled":
            order = literal_column("enrolled_count").desc()
        else:
            order = Sequence.created_at.desc()

        rows_result = await self._db.execute(
            base.order_by(order).limit(limit).offset(offset)
        )
        rows = rows_result.all()
        items = [
            {
                "id": row.id,
                "name": row.name,
                "status": row.status,
                "created_at": row.created_at,
                "step_count": int(row.step_count),
                "enrolled_count": int(row.enrolled_count),
                "replied_count": int(row.replied_count),
            }
            for row in rows
        ]
        return items, total

    async def create(self, **kwargs: Any) -> Sequence:
        seq = Sequence(**kwargs)
        self._db.add(seq)
        await self._db.flush()
        return seq

    async def create_steps(
        self,
        sequence_id: uuid.UUID,
        steps_data: Iterable[Mapping[str, Any]],
    ) -> list[SequenceStep]:
        created = [
            SequenceStep(
                sequence_id=sequence_id,
                step_order=step_order,
                subject=raw["subject"],
                body_html=raw["body_html"],
                delay_minutes=int(raw["delay_minutes"]),
            )
            for step_order, raw in enumerate(steps_data)
        ]
        self._db.add_all(created)
        await self._db.flush()
        return created

    async def replace_steps(
        self,
        sequence_id: uuid.UUID,
        steps_data: Iterable[Mapping[str, Any]],
    ) -> list[SequenceStep]:
        await self._db.execute(
            delete(SequenceStep).where(SequenceStep.sequence_id == sequence_id)
        )
        await self._db.flush()
        return await self.create_steps(sequence_id, steps_data)

    async def delete(self, sequence_id: uuid.UUID) -> None:
        enrollment_ids = select(Enrollment.id).where(
            Enrollment.sequence_id == sequence_id
        )
        event_ids = select(EmailEvent.id).where(
            EmailEvent.enrollment_id.in_(enrollment_ids)
        )
        await self._db.execute(
            delete(Referral).where(Referral.source_email_event_id.in_(event_ids))
        )
        await self._db.execute(
            delete(StateTransition).where(StateTransition.enrollment_id.in_(enrollment_ids))
        )
        await self._db.execute(
            delete(EmailEvent).where(EmailEvent.enrollment_id.in_(enrollment_ids))
        )
        await self._db.execute(
            delete(Enrollment).where(Enrollment.sequence_id == sequence_id)
        )
        await self._db.execute(
            delete(SequenceStep).where(SequenceStep.sequence_id == sequence_id)
        )
        await self._db.execute(
            delete(Sequence).where(Sequence.id == sequence_id)
        )
        await self._db.flush()

    async def update(self, sequence: Sequence, **kwargs: Any) -> Sequence:
        column_keys = {attr.key for attr in class_mapper(Sequence).column_attrs}
        unknown = sorted(name for name in kwargs if name not in column_keys)
        if unknown:
            raise ValueError("Unknown fields for Sequence update: " + ", ".join(unknown))
        for key, value in kwargs.items():
            setattr(sequence, key, value)
        await self._db.flush()
        return sequence
