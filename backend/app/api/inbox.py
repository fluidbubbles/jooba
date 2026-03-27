from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import get_db
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.sequence_repo import SequenceRepository
from app.schemas.email_event import InboxReplyItem, ReplyDetail, SentimentCounts, ThreadEvent
from app.schemas.enrollment import EnrollResponse
from app.schemas.referral import ReferralEnrollRequest, ReferralInfo
from app.services.exceptions import DomainError
from app.services.referral_service import ReferralService
from app.tasks.dispatcher import get_dispatcher
from app.utils.formatting import format_candidate_name

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.get("/replies", response_model=list[InboxReplyItem])
async def list_inbox_replies(
    sentiment: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    event_repo = EmailEventRepository(db)

    unreplied_ids = set(await event_repo.get_unreplied_inbound(
        sentiments=["interested", "referral", "neutral"],
        older_than_minutes=settings.unreplied_threshold_minutes,
    ))

    is_unreplied_filter = sentiment == "unreplied"
    db_sentiment = None if is_unreplied_filter else sentiment
    replies = await event_repo.get_inbox_replies(db_sentiment, limit, offset)

    items = [
        InboxReplyItem(
            **r,
            candidate_name=format_candidate_name(
                r["first_name"], r["last_name"], r["candidate_email"]
            ),
            is_unreplied=UUID(r["id"]) in unreplied_ids,
        )
        for r in replies
    ]

    if is_unreplied_filter:
        items = [i for i in items if i.is_unreplied]

    return items


@router.get("/counts", response_model=SentimentCounts)
async def get_sentiment_counts(db: AsyncSession = Depends(get_db)):
    event_repo = EmailEventRepository(db)
    counts = await event_repo.get_sentiment_counts()
    unreplied_ids = await event_repo.get_unreplied_inbound(
        sentiments=["interested", "referral", "neutral"],
        older_than_minutes=settings.unreplied_threshold_minutes,
    )
    counts["unreplied"] = len(unreplied_ids)
    return counts


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
    "/replies/{email_event_id}/referral/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_referral_extraction(
    email_event_id: UUID, db: AsyncSession = Depends(get_db)
):
    """Dispatch referral extraction as an async task and return immediately."""
    event_repo = EmailEventRepository(db)
    event = await event_repo.find_by_id(email_event_id)
    if not event:
        raise DomainError("Reply not found", "REPLY_NOT_FOUND")

    get_dispatcher().dispatch(
        "app.tasks.referral.extract_referral",
        str(email_event_id),
        queue="ai",
    )
    return {"status": "accepted"}


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
    result = await referral_service.enroll_referred(email_event_id, body.sequence_id)
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
