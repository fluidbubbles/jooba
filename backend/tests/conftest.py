import os
from collections.abc import AsyncGenerator
from urllib.parse import urlparse

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL must be set for integration tests")

# Tables listed in FK-safe order; CASCADE handles dependents automatically.
# nylas_accounts is excluded — the user's real OAuth connection must survive test runs.
_TRUNCATE_TABLES = "sequences, candidates"


def _validate_truncate_target(database_url: str) -> None:
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/")
    host = parsed.hostname or ""
    db_name_lower = db_name.lower()

    allow_truncate = os.getenv("ALLOW_TEST_DB_TRUNCATE") == "1"
    looks_like_test_db = (
        db_name_lower == "test"
        or db_name_lower.startswith("test_")
        or db_name_lower.endswith("_test")
    )
    is_local_target = host in {"localhost", "127.0.0.1", "db"}

    safe_to_truncate = is_local_target and (looks_like_test_db or allow_truncate)
    if not safe_to_truncate:
        raise RuntimeError(
            "Refusing TRUNCATE on non-test DB. Use a local *_test database "
            "or set ALLOW_TEST_DB_TRUNCATE=1 explicitly."
        )


_validate_truncate_target(TEST_DATABASE_URL)


@pytest_asyncio.fixture
async def _isolated_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    # Per-test engine avoids cross-event-loop asyncpg failures.
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def truncate() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text(f"TRUNCATE TABLE {_TRUNCATE_TABLES} RESTART IDENTITY CASCADE")
            )

    await truncate()
    try:
        yield session_factory
    finally:
        await truncate()
        await engine.dispose()


@pytest_asyncio.fixture
async def client(
    _isolated_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    async def _get_db_override() -> AsyncGenerator[AsyncSession, None]:
        async with _isolated_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _get_db_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    if previous_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_override
