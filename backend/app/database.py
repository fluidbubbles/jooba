from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Celery tasks use asyncio.run() which creates a new event loop per call.
# The module-level engine's pool is bound to the import-time loop, causing
# "Future attached to a different loop" errors. NullPool creates a fresh
# connection per use and closes it immediately — no pool state to conflict.
celery_engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
celery_session = async_sessionmaker(celery_engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
