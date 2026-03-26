from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.enrollment import (
    EnrollRequest,
    EnrollResponse,
    PaginatedEnrollments,
    SequenceAnalytics,
)
from app.services.enrollment_service import EnrollmentService

router = APIRouter(prefix="/api/sequences", tags=["enrollments"])


def get_enrollment_service(db: AsyncSession = Depends(get_db)) -> EnrollmentService:
    return EnrollmentService(db)


EnrollmentServiceDep = Annotated[EnrollmentService, Depends(get_enrollment_service)]


@router.post("/{sequence_id}/enroll", response_model=EnrollResponse, status_code=201)
async def enroll_candidates(
    sequence_id: UUID,
    data: EnrollRequest,
    service: EnrollmentServiceDep,
) -> EnrollResponse:
    result = await service.enroll_candidates(sequence_id, data.candidates)
    return EnrollResponse(**result)


@router.get("/{sequence_id}/enrollments", response_model=PaginatedEnrollments)
async def list_enrollments(
    sequence_id: UUID,
    service: EnrollmentServiceDep,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedEnrollments:
    items, total = await service.list_enrollments(
        sequence_id, status, limit, offset
    )
    return PaginatedEnrollments(items=items, total=total)


@router.get("/{sequence_id}/analytics", response_model=SequenceAnalytics)
async def get_sequence_analytics(
    sequence_id: UUID,
    service: EnrollmentServiceDep,
) -> SequenceAnalytics:
    result = await service.get_analytics(sequence_id)
    return SequenceAnalytics(**result)
