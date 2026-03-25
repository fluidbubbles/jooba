from fastapi import APIRouter
from sqlalchemy import text

from app.database import async_session

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    async with async_session() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
