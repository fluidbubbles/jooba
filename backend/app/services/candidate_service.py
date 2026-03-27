import re
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.candidate_repo import CandidateRepository
from app.repositories.email_event_repo import EmailEventRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.referral_repo import ReferralRepository
from app.services.exceptions import CandidateNotFound, EnrollmentNotFound
from app.utils.formatting import format_candidate_name

_BODY_SNIPPET_LEN = 150
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _body_snippet(body_text: str | None, body_html: str | None) -> str:
    if body_text:
        return body_text[:_BODY_SNIPPET_LEN]
    if body_html:
        return _HTML_TAG_RE.sub("", body_html)[:_BODY_SNIPPET_LEN]
    return ""


class CandidateService:
    def __init__(self, db: AsyncSession) -> None:
        self._enrollment_repo = EnrollmentRepository(db)
        self._candidate_repo = CandidateRepository(db)
        self._event_repo = EmailEventRepository(db)
        self._referral_repo = ReferralRepository(db)

    async def get_timeline(self, enrollment_id: UUID) -> dict:
        enrollment = await self._enrollment_repo.get_by_id(enrollment_id)
        if enrollment is None:
            raise EnrollmentNotFound(enrollment_id)

        candidate = await self._candidate_repo.get_by_id(enrollment.candidate_id)
        if candidate is None:
            raise CandidateNotFound(str(enrollment.candidate_id))

        transitions = await self._enrollment_repo.list_state_transitions(enrollment_id)
        events = await self._event_repo.get_thread(enrollment_id)

        items: list[tuple[datetime, dict]] = []
        for t in transitions:
            items.append(
                (
                    t.created_at,
                    {
                        "type": "transition",
                        "timestamp": t.created_at,
                        "from_status": t.from_status,
                        "to_status": t.to_status,
                        "trigger": t.trigger,
                    },
                )
            )
        for e in events:
            items.append(
                (
                    e.created_at,
                    {
                        "type": "email",
                        "timestamp": e.created_at,
                        "direction": e.direction,
                        "subject": e.subject,
                        "body_snippet": _body_snippet(e.body_text, e.body_html),
                        "sentiment": e.sentiment,
                        "step_index": e.step_index,
                        "is_manual_reply": e.is_manual_reply,
                    },
                )
            )

        items.sort(key=lambda pair: pair[0])
        timeline = [entry for _, entry in items]

        referral_row = await self._referral_repo.get_by_referred_candidate(candidate.id)
        referral_info = None
        if referral_row is not None:
            referrer = await self._candidate_repo.get_by_id(
                referral_row.referrer_candidate_id
            )
            if referrer is not None:
                referral_info = {
                    "referrer_name": format_candidate_name(
                        referrer.first_name, referrer.last_name, referrer.email
                    ),
                    "referrer_email": referrer.email,
                }

        return {
            "candidate": {
                "name": format_candidate_name(
                    candidate.first_name, candidate.last_name, candidate.email
                ),
                "email": candidate.email,
                "company": candidate.company,
                "title": candidate.title,
            },
            "enrollment_status": enrollment.status,
            "timeline": timeline,
            "referral": referral_info,
        }
