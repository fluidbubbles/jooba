from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import get_db
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.sequence_repo import SequenceRepository
from app.schemas.email_event import InboxReplyItem, ReplyDetail, SentimentCounts, ThreadEvent
from app.services.exceptions import DomainError
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
    replies = await event_repo.get_inbox_replies(sentiment, limit, offset)

    unreplied_ids = set(await event_repo.get_unreplied_inbound(
        sentiments=["interested", "referral", "neutral"],
        older_than_minutes=settings.unreplied_threshold_minutes,
    ))

    return [
        InboxReplyItem(**r, is_unreplied=UUID(r["id"]) in unreplied_ids)
        for r in replies
    ]


@router.get("/counts", response_model=SentimentCounts)
async def get_sentiment_counts(db: AsyncSession = Depends(get_db)):
    event_repo = EmailEventRepository(db)
    return await event_repo.get_sentiment_counts()


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
        sentiment=event.sentiment,
        sentiment_reasoning=event.sentiment_reasoning,
        thread=[ThreadEvent.model_validate(e) for e in thread],
    )
