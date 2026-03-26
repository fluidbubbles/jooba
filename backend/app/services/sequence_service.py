import uuid
from typing import Any

from app.models.enums import SequenceStatus
from app.models.sequence import Sequence
from app.repositories.sequence_repo import SequenceRepository
from app.schemas.sequence import SequenceCreate, SequenceUpdate, StepInput
from app.services.exceptions import (
    InvalidSequenceData,
    InvalidStateTransition,
    SequenceNotFound,
)

VALID_SEQUENCE_TRANSITIONS: dict[SequenceStatus, list[SequenceStatus]] = {
    SequenceStatus.DRAFT: [SequenceStatus.ACTIVE],
    SequenceStatus.ACTIVE: [SequenceStatus.PAUSED],
    SequenceStatus.PAUSED: [SequenceStatus.ACTIVE, SequenceStatus.ARCHIVED],
    SequenceStatus.ARCHIVED: [],
}

_SEQUENCE_UPDATE_OPTIONAL_FIELDS: tuple[str, ...] = (
    "role_title",
    "company",
)


class SequenceService:
    def __init__(self, repo: SequenceRepository) -> None:
        self._repo = repo

    async def _reload_sequence(self, sequence_id: uuid.UUID) -> Sequence:
        reloaded = await self._repo.get_by_id(sequence_id)
        if reloaded is None:
            raise SequenceNotFound(sequence_id)
        return reloaded

    def _validate_steps(self, steps: list[StepInput]) -> None:
        if not steps:
            raise InvalidSequenceData("Sequence must have at least one step")
        if steps[0].delay != 0:
            raise InvalidSequenceData("First step must have delay equal to 0")

    def _step_payloads(self, steps: list[StepInput]) -> list[dict[str, Any]]:
        return [
            {
                "subject": step.subject,
                "body_html": step.body_html,
                "delay_minutes": step.delay,
            }
            for step in steps
        ]

    def _steps_for_validation(self, seq: Sequence) -> list[StepInput]:
        return [
            StepInput(
                subject=step.subject,
                body_html=step.body_html,
                delay=step.delay_minutes,
            )
            for step in seq.steps
        ]

    def _sequence_update_payload(self, data: SequenceUpdate) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if data.name is not None:
            updates["name"] = data.name
        for field in _SEQUENCE_UPDATE_OPTIONAL_FIELDS:
            if field in data.model_fields_set:
                updates[field] = getattr(data, field)
        return updates

    async def create(self, data: SequenceCreate) -> Sequence:
        self._validate_steps(data.steps)
        fields = data.model_dump(exclude={"steps"})
        seq = await self._repo.create(
            **fields,
            status=SequenceStatus.DRAFT.value,
        )
        await self._repo.create_steps(seq.id, self._step_payloads(data.steps))
        return await self._reload_sequence(seq.id)

    async def get(self, sequence_id: uuid.UUID) -> Sequence:
        seq = await self._repo.get_by_id(sequence_id)
        if seq is None:
            raise SequenceNotFound(sequence_id)
        return seq

    async def list_all(
        self,
        *,
        q: str | None = None,
        status: SequenceStatus | None = None,
        sort: str = "created",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        return await self._repo.list_paginated(
            q=q,
            status=status.value if status else None,
            sort=sort,
            limit=limit,
            offset=offset,
        )

    async def update(self, sequence_id: uuid.UUID, data: SequenceUpdate) -> Sequence:
        seq = await self.get(sequence_id)
        current = SequenceStatus(seq.status)
        if current is not SequenceStatus.DRAFT:
            raise InvalidStateTransition(current.value, "edit")

        updates = self._sequence_update_payload(data)
        if updates:
            await self._repo.update(seq, **updates)

        if "steps" in data.model_fields_set and data.steps is not None:
            self._validate_steps(data.steps)
            await self._repo.replace_steps(sequence_id, self._step_payloads(data.steps))

        return await self._reload_sequence(sequence_id)

    async def delete(self, sequence_id: uuid.UUID) -> None:
        await self.get(sequence_id)  # raises SequenceNotFound if missing
        await self._repo.delete(sequence_id)

    async def change_status(
        self, sequence_id: uuid.UUID, new_status: SequenceStatus
    ) -> Sequence:
        seq = await self.get(sequence_id)
        current = SequenceStatus(seq.status)
        allowed = VALID_SEQUENCE_TRANSITIONS[current]
        if new_status not in allowed:
            raise InvalidStateTransition(current.value, new_status.value)
        if new_status is SequenceStatus.ACTIVE:
            self._validate_steps(self._steps_for_validation(seq))
        await self._repo.update(seq, status=new_status.value)
        return await self._reload_sequence(sequence_id)
