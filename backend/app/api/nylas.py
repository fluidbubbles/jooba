import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import get_db
from app.integrations.nylas_client import NylasClient
from app.repositories.nylas_account_repo import NylasAccountRepository
from app.schemas.nylas import NylasAuthUrl, NylasConnectionStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nylas", tags=["nylas"])


@router.get("/auth-url", response_model=NylasAuthUrl)
async def get_auth_url() -> dict:
    """Generate Nylas OAuth URL for the frontend to redirect to."""
    client = NylasClient()
    url = client.get_auth_url()
    return {"url": url}


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...), db: AsyncSession = Depends(get_db)
) -> RedirectResponse:
    """Handle OAuth callback from Nylas. Saves grant_id, redirects to settings."""
    try:
        client = NylasClient()
        grant_data = client.exchange_code_for_grant(code)
    except Exception:
        logger.exception("Nylas OAuth code exchange failed")
        return RedirectResponse(url=f"{settings.frontend_url}/settings?error=auth_failed")

    repo = NylasAccountRepository(db)
    await repo.delete_all()
    await repo.create(
        grant_id=grant_data["grant_id"],
        email=grant_data["email"],
    )

    return RedirectResponse(url=f"{settings.frontend_url}/settings?connected=true")


@router.get("/status", response_model=NylasConnectionStatus)
async def get_connection_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Check if an email account is connected."""
    repo = NylasAccountRepository(db)
    account = await repo.get_first()
    if not account:
        return {"connected": False}
    return {
        "connected": True,
        "email": account.email,
        "provider": account.provider,
        "connected_at": account.connected_at,
    }


@router.delete("/disconnect")
async def disconnect(db: AsyncSession = Depends(get_db)) -> dict:
    """Disconnect the email account."""
    repo = NylasAccountRepository(db)
    await repo.delete_all()
    return {"status": "disconnected"}
