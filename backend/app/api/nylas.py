import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import get_db
from app.schemas.nylas import NylasAuthUrl, NylasConnectionStatus, NylasDisconnectResponse
from app.services.exceptions import PermanentError, ProviderRateLimited, TransientError
from app.services.nylas_connection_service import NylasConnectionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nylas", tags=["nylas"])


def _settings_redirect(query: str) -> RedirectResponse:
    return RedirectResponse(url=f"{settings.frontend_url}/settings{query}")


def get_nylas_connection_service(
    db: AsyncSession = Depends(get_db),
) -> NylasConnectionService:
    return NylasConnectionService(db)


@router.get("/auth-url", response_model=NylasAuthUrl)
async def get_auth_url(
    service: NylasConnectionService = Depends(get_nylas_connection_service),
) -> NylasAuthUrl:
    """Generate Nylas OAuth URL for the frontend to redirect to."""
    return NylasAuthUrl(url=service.get_auth_url())


@router.get("/callback")
async def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    service: NylasConnectionService = Depends(get_nylas_connection_service),
) -> RedirectResponse:
    """Handle OAuth callback from Nylas. Saves grant_id, redirects to settings."""
    if error:
        logger.warning("Nylas OAuth callback returned provider error: %s", error)
        return _settings_redirect("?error=oauth_denied")

    if not code:
        logger.error("Nylas OAuth callback missing code")
        return _settings_redirect("?error=auth_failed")

    if not service.validate_oauth_state(state):
        logger.warning("Nylas OAuth callback failed state validation")
        return _settings_redirect("?error=invalid_state")

    try:
        await service.complete_oauth_callback(code)
    except ProviderRateLimited:
        logger.warning("Nylas OAuth callback rate limited")
        return _settings_redirect("?error=provider_rate_limited")
    except TransientError:
        logger.warning("Nylas OAuth callback transient failure")
        return _settings_redirect("?error=auth_temporary")
    except PermanentError:
        logger.warning("Nylas OAuth callback permanent failure")
        return _settings_redirect("?error=auth_failed")
    except Exception:
        logger.exception("Nylas OAuth callback handling failed")
        return _settings_redirect("?error=auth_failed")

    return _settings_redirect("?connected=true")


@router.get("/status", response_model=NylasConnectionStatus)
async def get_connection_status(
    service: NylasConnectionService = Depends(get_nylas_connection_service),
) -> NylasConnectionStatus:
    """Check if an email account is connected."""
    return await service.get_connection_status()


@router.delete("/disconnect", response_model=NylasDisconnectResponse)
async def disconnect(
    service: NylasConnectionService = Depends(get_nylas_connection_service),
) -> NylasDisconnectResponse:
    """Disconnect the email account."""
    await service.disconnect()
    return NylasDisconnectResponse()
