import os
from collections.abc import AsyncGenerator
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL must be set for integration tests")


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
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def truncate() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text("TRUNCATE TABLE sequences, candidates RESTART IDENTITY CASCADE")
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


async def _create_active_sequence(client: AsyncClient) -> str:
    """Helper: create a sequence and activate it, returning the sequence id."""
    seq = await client.post("/api/sequences", json={
        "name": "Test Sequence",
        "steps": [{"subject": "Hi", "body_html": "<p>Hello</p>", "delay": 0}],
    })
    assert seq.status_code == 201
    seq_id = seq.json()["id"]

    activate = await client.put(f"/api/sequences/{seq_id}/status", json={"status": "active"})
    assert activate.status_code == 200
    return seq_id


class TestEnrollCandidates:
    @pytest.mark.asyncio
    async def test_enroll_happy_path(self, client: AsyncClient) -> None:
        seq_id = await _create_active_sequence(client)
        response = await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [
                {"email": "jane@example.com", "first_name": "Jane"},
                {"email": "alex@example.com", "first_name": "Alex"},
            ],
        })
        assert response.status_code == 201
        body = response.json()
        assert body["enrolled"] == 2
        assert body["skipped"] == 0
        assert body["total"] == 2

    @pytest.mark.asyncio
    async def test_enroll_deduplicates_within_batch(self, client: AsyncClient) -> None:
        seq_id = await _create_active_sequence(client)
        response = await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [
                {"email": "jane@example.com"},
                {"email": "Jane@Example.com"},
            ],
        })
        assert response.status_code == 201
        body = response.json()
        assert body["enrolled"] == 1
        assert body["total"] == 2

    @pytest.mark.asyncio
    async def test_enroll_skips_already_enrolled(self, client: AsyncClient) -> None:
        seq_id = await _create_active_sequence(client)
        await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [{"email": "jane@example.com"}],
        })
        response = await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [{"email": "jane@example.com"}],
        })
        assert response.status_code == 201
        body = response.json()
        assert body["enrolled"] == 0
        assert body["skipped"] == 1

    @pytest.mark.asyncio
    async def test_enroll_requires_active_sequence(self, client: AsyncClient) -> None:
        seq = await client.post("/api/sequences", json={
            "name": "Draft",
            "steps": [{"subject": "Hi", "body_html": "<p>Hello</p>", "delay": 0}],
        })
        seq_id = seq.json()["id"]
        response = await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [{"email": "test@example.com"}],
        })
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_SEQUENCE_DATA"

    @pytest.mark.asyncio
    async def test_enroll_empty_candidates_rejected(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/sequences/00000000-0000-0000-0000-000000000001/enroll",
            json={"candidates": []},
        )
        assert response.status_code == 422


class TestListEnrollments:
    @pytest.mark.asyncio
    async def test_list_enrollments_after_enroll(self, client: AsyncClient) -> None:
        seq_id = await _create_active_sequence(client)
        await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [
                {"email": "jane@example.com", "first_name": "Jane", "last_name": "Chen"},
            ],
        })
        response = await client.get(f"/api/sequences/{seq_id}/enrollments")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["candidate_email"] == "jane@example.com"
        assert item["candidate_name"] == "Jane Chen"
        assert item["status"] == "active"
        assert item["current_step"] == 0

    @pytest.mark.asyncio
    async def test_list_empty_for_new_sequence(self, client: AsyncClient) -> None:
        seq_id = await _create_active_sequence(client)
        response = await client.get(f"/api/sequences/{seq_id}/enrollments")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0
        assert body["items"] == []


class TestSequenceAnalytics:
    @pytest.mark.asyncio
    async def test_analytics_for_new_sequence(self, client: AsyncClient) -> None:
        seq_id = await _create_active_sequence(client)
        response = await client.get(f"/api/sequences/{seq_id}/analytics")
        assert response.status_code == 200
        body = response.json()
        assert body["enrolled"] == 0
        assert body["sent"] == 0

    @pytest.mark.asyncio
    async def test_analytics_after_enrollment(self, client: AsyncClient) -> None:
        seq_id = await _create_active_sequence(client)
        await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [{"email": "a@b.com"}, {"email": "c@d.com"}],
        })
        response = await client.get(f"/api/sequences/{seq_id}/analytics")
        assert response.status_code == 200
        body = response.json()
        assert body["enrolled"] == 2

    @pytest.mark.asyncio
    async def test_analytics_404_for_missing_sequence(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/sequences/00000000-0000-0000-0000-000000000099/analytics"
        )
        assert response.status_code == 404
