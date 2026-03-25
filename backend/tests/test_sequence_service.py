from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.models.enums import SequenceStatus
from app.models.sequence import Sequence
from app.schemas.sequence import SequenceCreate, SequenceUpdate, StepInput
from app.services import VALID_SEQUENCE_TRANSITIONS, SequenceService
from app.services.exceptions import (
    InvalidSequenceData,
    InvalidStateTransition,
    SequenceNotFound,
)


def _sequence_service_with_mock_repo() -> tuple[SequenceService, AsyncMock]:
    mock_repo = AsyncMock()
    service = SequenceService(mock_repo)
    return service, mock_repo


def test_valid_sequence_transitions_mapping() -> None:
    assert VALID_SEQUENCE_TRANSITIONS[SequenceStatus.DRAFT] == [SequenceStatus.ACTIVE]
    assert VALID_SEQUENCE_TRANSITIONS[SequenceStatus.ACTIVE] == [SequenceStatus.PAUSED]
    assert set(VALID_SEQUENCE_TRANSITIONS[SequenceStatus.PAUSED]) == {
        SequenceStatus.ACTIVE,
        SequenceStatus.ARCHIVED,
    }
    assert VALID_SEQUENCE_TRANSITIONS[SequenceStatus.ARCHIVED] == []


def test_invalid_transitions_not_in_mapping() -> None:
    assert SequenceStatus.PAUSED not in VALID_SEQUENCE_TRANSITIONS[SequenceStatus.DRAFT]
    assert (
        SequenceStatus.ARCHIVED not in VALID_SEQUENCE_TRANSITIONS[SequenceStatus.DRAFT]
    )
    assert SequenceStatus.ACTIVE not in VALID_SEQUENCE_TRANSITIONS[SequenceStatus.ACTIVE]


def test_sequence_create_rejects_empty_steps_sync() -> None:
    with pytest.raises(ValidationError):
        SequenceCreate(name="Campaign", steps=[])


@pytest.mark.asyncio
async def test_create_rejects_first_step_delay_not_zero() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()

    data = SequenceCreate(
        name="N",
        steps=[
            StepInput(subject="a", body_html="<p>a</p>", delay=1),
            StepInput(subject="b", body_html="<p>b</p>", delay=0),
        ],
    )
    with pytest.raises(InvalidSequenceData):
        await service.create(data)
    mock_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_raises_sequence_not_found() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()
    mock_repo.get_by_id = AsyncMock(return_value=None)

    sid = uuid.uuid4()
    with pytest.raises(SequenceNotFound):
        await service.get(sid)
    mock_repo.get_by_id.assert_awaited_once_with(sid)


@pytest.mark.asyncio
async def test_update_rejects_non_draft() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()
    seq = MagicMock(spec=Sequence)
    seq.id = uuid.uuid4()
    seq.status = SequenceStatus.ACTIVE.value
    mock_repo.get_by_id = AsyncMock(return_value=seq)

    with pytest.raises(InvalidStateTransition):
        await service.update(seq.id, SequenceUpdate())


@pytest.mark.asyncio
async def test_change_status_rejects_invalid_transition() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()
    seq = MagicMock(spec=Sequence)
    seq.id = uuid.uuid4()
    seq.status = SequenceStatus.DRAFT.value
    seq.steps = [
        StepInput(subject="s", body_html="<p>x</p>", delay=0),
    ]
    mock_repo.get_by_id = AsyncMock(return_value=seq)

    with pytest.raises(InvalidStateTransition):
        await service.change_status(seq.id, SequenceStatus.ARCHIVED)


@pytest.mark.asyncio
async def test_activate_rejects_no_steps() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()
    seq = MagicMock(spec=Sequence)
    seq.id = uuid.uuid4()
    seq.status = SequenceStatus.DRAFT.value
    seq.steps = []
    mock_repo.get_by_id = AsyncMock(return_value=seq)

    with pytest.raises(InvalidSequenceData):
        await service.change_status(seq.id, SequenceStatus.ACTIVE)
    mock_repo.update.assert_not_awaited()


def _mock_step(
    *,
    subject: str = "s",
    body_html: str = "<p>x</p>",
    delay_minutes: int = 0,
    step_order: int = 0,
) -> MagicMock:
    step = MagicMock()
    step.subject = subject
    step.body_html = body_html
    step.delay_minutes = delay_minutes
    step.step_order = step_order
    return step


@pytest.mark.asyncio
async def test_change_status_draft_to_active_success() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()
    seq_id = uuid.uuid4()
    seq = MagicMock(spec=Sequence)
    seq.id = seq_id
    seq.status = SequenceStatus.DRAFT.value
    seq.steps = [_mock_step()]
    reloaded = MagicMock(spec=Sequence)
    reloaded.id = seq_id
    reloaded.status = SequenceStatus.ACTIVE.value
    mock_repo.get_by_id = AsyncMock(side_effect=[seq, reloaded])

    result = await service.change_status(seq_id, SequenceStatus.ACTIVE)

    assert result is reloaded
    mock_repo.update.assert_awaited_once_with(
        seq, status=SequenceStatus.ACTIVE.value
    )


@pytest.mark.asyncio
async def test_change_status_active_to_paused_success() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()
    seq_id = uuid.uuid4()
    seq = MagicMock(spec=Sequence)
    seq.id = seq_id
    seq.status = SequenceStatus.ACTIVE.value
    seq.steps = [_mock_step()]
    reloaded = MagicMock(spec=Sequence)
    reloaded.id = seq_id
    reloaded.status = SequenceStatus.PAUSED.value
    mock_repo.get_by_id = AsyncMock(side_effect=[seq, reloaded])

    result = await service.change_status(seq_id, SequenceStatus.PAUSED)

    assert result is reloaded
    mock_repo.update.assert_awaited_once_with(
        seq, status=SequenceStatus.PAUSED.value
    )


@pytest.mark.asyncio
async def test_change_status_paused_to_active_success() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()
    seq_id = uuid.uuid4()
    seq = MagicMock(spec=Sequence)
    seq.id = seq_id
    seq.status = SequenceStatus.PAUSED.value
    seq.steps = [_mock_step(), _mock_step(subject="t", step_order=1, delay_minutes=60)]
    reloaded = MagicMock(spec=Sequence)
    reloaded.id = seq_id
    reloaded.status = SequenceStatus.ACTIVE.value
    mock_repo.get_by_id = AsyncMock(side_effect=[seq, reloaded])

    result = await service.change_status(seq_id, SequenceStatus.ACTIVE)

    assert result is reloaded
    mock_repo.update.assert_awaited_once_with(
        seq, status=SequenceStatus.ACTIVE.value
    )


@pytest.mark.asyncio
async def test_change_status_paused_to_archived_success() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()
    seq_id = uuid.uuid4()
    seq = MagicMock(spec=Sequence)
    seq.id = seq_id
    seq.status = SequenceStatus.PAUSED.value
    seq.steps = [_mock_step()]
    reloaded = MagicMock(spec=Sequence)
    reloaded.id = seq_id
    reloaded.status = SequenceStatus.ARCHIVED.value
    mock_repo.get_by_id = AsyncMock(side_effect=[seq, reloaded])

    result = await service.change_status(seq_id, SequenceStatus.ARCHIVED)

    assert result is reloaded
    mock_repo.update.assert_awaited_once_with(
        seq, status=SequenceStatus.ARCHIVED.value
    )


@pytest.mark.asyncio
async def test_activate_rejects_first_step_delay_not_zero() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()
    seq_id = uuid.uuid4()
    seq = MagicMock(spec=Sequence)
    seq.id = seq_id
    seq.status = SequenceStatus.DRAFT.value
    seq.steps = [
        _mock_step(delay_minutes=30),
        _mock_step(subject="b", step_order=1, delay_minutes=0),
    ]
    mock_repo.get_by_id = AsyncMock(return_value=seq)

    with pytest.raises(InvalidSequenceData):
        await service.change_status(seq_id, SequenceStatus.ACTIVE)
    mock_repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_draft_success_updates_and_replaces_steps() -> None:
    service, mock_repo = _sequence_service_with_mock_repo()
    seq_id = uuid.uuid4()
    seq = MagicMock(spec=Sequence)
    seq.id = seq_id
    seq.status = SequenceStatus.DRAFT.value
    mock_repo.get_by_id = AsyncMock(
        side_effect=[
            seq,
            seq,
        ]
    )

    new_steps = [
        StepInput(subject="a", body_html="<p>a</p>", delay=0),
        StepInput(subject="b", body_html="<p>b</p>", delay=1440),
    ]
    data = SequenceUpdate(
        name="Renamed",
        role_title="Engineer",
        company="Acme",
        steps=new_steps,
    )

    result = await service.update(seq_id, data)

    assert result is seq
    mock_repo.update.assert_awaited_once_with(
        seq,
        name="Renamed",
        role_title="Engineer",
        company="Acme",
    )
    mock_repo.replace_steps.assert_awaited_once_with(
        seq_id,
        [
            {"subject": "a", "body_html": "<p>a</p>", "delay_minutes": 0},
            {"subject": "b", "body_html": "<p>b</p>", "delay_minutes": 1440},
        ],
    )
