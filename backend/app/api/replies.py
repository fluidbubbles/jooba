from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.email_event import ManualReplyInput
from app.services.email_service import EmailService

router = APIRouter(prefix="/api/replies", tags=["replies"])


@router.post("/{email_event_id}/reply")
async def send_manual_reply(
    email_event_id: UUID, data: ManualReplyInput, db: AsyncSession = Depends(get_db),
):
    service = EmailService(db)
    return await service.send_manual_reply(email_event_id, data.body_html)
