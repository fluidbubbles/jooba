import logging

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.enrollment_service import EnrollmentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["unsubscribe"])

UNSUBSCRIBE_SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head><title>Unsubscribed</title></head>
<body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#f5f5f5;">
  <div style="text-align:center;padding:40px;background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
    <h2>You've been unsubscribed</h2>
    <p style="color:#6b7280;">You will no longer receive emails from this sequence.</p>
  </div>
</body>
</html>"""

UNSUBSCRIBE_ERROR_HTML = """<!DOCTYPE html>
<html>
<head><title>Unsubscribe</title></head>
<body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#f5f5f5;">
  <div style="text-align:center;padding:40px;background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
    <h2>Invalid unsubscribe link</h2>
    <p style="color:#6b7280;">This link may have expired or is invalid.</p>
  </div>
</body>
</html>"""


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        success = await EnrollmentService(db).opt_out(token)
    except Exception:
        await db.rollback()
        logger.exception("Unsubscribe failed for token=%s", token[:16])
        return HTMLResponse(UNSUBSCRIBE_ERROR_HTML, status_code=500)
    if success:
        return HTMLResponse(UNSUBSCRIBE_SUCCESS_HTML)
    return HTMLResponse(UNSUBSCRIBE_ERROR_HTML, status_code=400)
