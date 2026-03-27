from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.candidate_timeline import EnrollmentTimelineResponse
from app.services.candidate_service import CandidateService


router = APIRouter(prefix="/api/enrollments", tags=["candidates"])


def get_candidate_service(db: AsyncSession = Depends(get_db)) -> CandidateService:
    return CandidateService(db)


CandidateServiceDep = Annotated[CandidateService, Depends(get_candidate_service)]


@router.get("/{enrollment_id}/timeline", response_model=EnrollmentTimelineResponse)
async def get_enrollment_timeline(
    enrollment_id: UUID,
    service: CandidateServiceDep,
) -> EnrollmentTimelineResponse:
    return EnrollmentTimelineResponse.model_validate(
        await service.get_timeline(enrollment_id)
    )
