from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import get_db
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.sequence_repo import SequenceRepository
from app.schemas.email_event import InboxReplyItem, ReplyDetail, SentimentCounts, ThreadEvent
from app.schemas.enrollment import CandidateInput, EnrollResponse
from app.schemas.referral import ReferralEnrollRequest, ReferralInfo
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import DomainError
from app.services.referral_service import ReferralService
from app.utils.formatting import format_candidate_name
from app.utils.name_parse import split_full_name

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.get("/replies", response_model=list[InboxReplyItem])
async def list_inbox_replies(
    sentiment: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    event_repo = EmailEventRepository(db)
    replies = await event_repo.get_inbox_replies(sentiment, limit, offset)

    unreplied_ids = set(await event_repo.get_unreplied_inbound(
        sentiments=["interested", "referral", "neutral"],
        older_than_minutes=settings.unreplied_threshold_minutes,
    ))

    return [
        InboxReplyItem(
            **r,
            candidate_name=format_candidate_name(
                r["first_name"], r["last_name"], r["candidate_email"]
            ),
            is_unreplied=UUID(r["id"]) in unreplied_ids,
        )
        for r in replies
    ]


@router.get("/counts", response_model=SentimentCounts)
async def get_sentiment_counts(db: AsyncSession = Depends(get_db)):
    event_repo = EmailEventRepository(db)
    return await event_repo.get_sentiment_counts()


@router.get(
    "/replies/{email_event_id}/referral",
    response_model=ReferralInfo | None,
)
async def get_reply_referral(email_event_id: UUID, db: AsyncSession = Depends(get_db)):
    referral_service = ReferralService(db)
    data = await referral_service.get_referral_for_event(email_event_id)
    if data is None:
        return None
    return ReferralInfo.model_validate(data)


@router.post(
    "/replies/{email_event_id}/referral/enroll",
    response_model=EnrollResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enroll_referred_candidate(
    email_event_id: UUID,
    body: ReferralEnrollRequest,
    db: AsyncSession = Depends(get_db),
) -> EnrollResponse:
    referral_service = ReferralService(db)
    referral = await referral_service.get_referral_for_event(email_event_id)
    if (
        referral is None
        or not referral.get("has_email")
        or not referral.get("email")
    ):
        raise DomainError(
            "Cannot enroll referral without email",
            "REFERRAL_NO_EMAIL",
        )

    first_name, last_name = split_full_name(referral["name"])
    try:
        candidate = CandidateInput(
            email=referral["email"],
            first_name=first_name,
            last_name=last_name,
            company=referral["company"],
            title=referral["title"],
        )
    except ValidationError:
        raise DomainError(
            "Invalid referral email or candidate data",
            "REFERRAL_INVALID_EMAIL",
        ) from None

    enrollment_service = EnrollmentService(db)
    result = await enrollment_service.enroll_candidates(body.sequence_id, [candidate])
    return EnrollResponse(**result)


@router.get("/replies/{email_event_id}", response_model=ReplyDetail)
async def get_reply_detail(email_event_id: UUID, db: AsyncSession = Depends(get_db)):
    event_repo = EmailEventRepository(db)
    enrollment_repo = EnrollmentRepository(db)
    candidate_repo = CandidateRepository(db)
    sequence_repo = SequenceRepository(db)

    event = await event_repo.find_by_id(email_event_id)
    if not event:
        raise DomainError("Reply not found", "REPLY_NOT_FOUND")

    enrollment = await enrollment_repo.get_by_id(event.enrollment_id)
    if not enrollment:
        raise DomainError("Enrollment not found", "ENROLLMENT_NOT_FOUND")
    candidate = await candidate_repo.get_by_id(enrollment.candidate_id)
    if not candidate:
        raise DomainError("Candidate not found", "CANDIDATE_NOT_FOUND")
    sequence = await sequence_repo.get_by_id(enrollment.sequence_id)
    if not sequence:
        raise DomainError("Sequence not found", "SEQUENCE_NOT_FOUND")

    thread = await event_repo.get_thread(enrollment.id)

    candidate_name = format_candidate_name(
        candidate.first_name, candidate.last_name, candidate.email
    )

    return ReplyDetail(
        enrollment_id=str(enrollment.id),
        candidate_name=candidate_name,
        candidate_email=candidate.email,
        sequence_name=sequence.name,
        current_step=enrollment.current_step,
        total_steps=len(sequence.steps),
        sentiment=event.sentiment,
        sentiment_reasoning=event.sentiment_reasoning,
        thread=[ThreadEvent.model_validate(e) for e in thread],
    )
