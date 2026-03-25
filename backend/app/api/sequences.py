from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.sequence import Sequence
from app.repositories.sequence_repo import SequenceRepository
from app.schemas.sequence import (
    SequenceCreate,
    SequenceListItem,
    SequenceResponse,
    SequenceStatusUpdate,
    SequenceUpdate,
)
from app.services.sequence_service import SequenceService

router = APIRouter(prefix="/api/sequences", tags=["sequences"])


def _to_response(seq: Sequence) -> SequenceResponse:
    return SequenceResponse.model_validate(seq)


def get_sequence_service(db: AsyncSession = Depends(get_db)) -> SequenceService:
    return SequenceService(SequenceRepository(db))


SequenceServiceDep = Annotated[SequenceService, Depends(get_sequence_service)]


@router.post("", response_model=SequenceResponse, status_code=status.HTTP_201_CREATED)
async def create_sequence(
    payload: SequenceCreate,
    service: SequenceServiceDep,
) -> SequenceResponse:
    seq = await service.create(payload)
    return _to_response(seq)


@router.get("", response_model=list[SequenceListItem])
async def list_sequences(
    service: SequenceServiceDep,
) -> list[SequenceListItem]:
    rows = await service.list_all()
    return [SequenceListItem.model_validate(row) for row in rows]


@router.get("/{sequence_id}", response_model=SequenceResponse)
async def get_sequence(
    sequence_id: UUID,
    service: SequenceServiceDep,
) -> SequenceResponse:
    seq = await service.get(sequence_id)
    return _to_response(seq)


@router.put("/{sequence_id}", response_model=SequenceResponse)
async def update_sequence(
    sequence_id: UUID,
    payload: SequenceUpdate | SequenceStatusUpdate,
    service: SequenceServiceDep,
) -> SequenceResponse:
    if isinstance(payload, SequenceStatusUpdate):
        seq = await service.change_status(sequence_id, payload.status)
    else:
        seq = await service.update(sequence_id, payload)
    return _to_response(seq)


@router.put("/{sequence_id}/status", response_model=SequenceResponse)
async def update_sequence_status(
    sequence_id: UUID,
    payload: SequenceStatusUpdate,
    service: SequenceServiceDep,
) -> SequenceResponse:
    seq = await service.change_status(sequence_id, payload.status)
    return _to_response(seq)
