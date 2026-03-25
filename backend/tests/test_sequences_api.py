from __future__ import annotations

import os
import uuid
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
    # Per-test engine avoids cross-event-loop asyncpg failures.
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def truncate() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE TABLE sequences RESTART IDENTITY CASCADE"))

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


def _step(delay: int = 0, subject: str = "Hello", body: str = "<p>Hi</p>") -> dict:
    return {"subject": subject, "body_html": body, "delay": delay}


async def _create_sequence_id(
    client: AsyncClient,
    *,
    name: str = "Seq",
    steps: list[dict] | None = None,
) -> str:
    payload = {"name": name, "steps": steps if steps is not None else [_step()]}
    r = await client.post("/api/sequences", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_create_success(client: AsyncClient) -> None:
    payload = {
        "name": "Outreach A",
        "steps": [_step()],
    }
    r = await client.post("/api/sequences", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Outreach A"
    assert data["status"] == "draft"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["delay"] == 0
    assert data["steps"][0]["subject"] == "Hello"


@pytest.mark.asyncio
async def test_list_returns_aggregate_counts(client: AsyncClient) -> None:
    await client.post(
        "/api/sequences",
        json={
            "name": "Multi",
            "steps": [_step(subject="a"), _step(subject="b", delay=60)],
        },
    )
    r = await client.get("/api/sequences")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["step_count"] == 2
    assert items[0]["enrolled_count"] == 0
    assert items[0]["replied_count"] == 0


@pytest.mark.asyncio
async def test_update_active_sequence_409(client: AsyncClient) -> None:
    sid = await _create_sequence_id(client, name="Seq")
    await client.put(f"/api/sequences/{sid}/status", json={"status": "active"})
    r = await client.put(f"/api/sequences/{sid}", json={"name": "Renamed"})
    assert r.status_code == 409
    assert r.json()["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_update_replaces_steps_response_returns_latest_steps(client: AsyncClient) -> None:
    sid = await _create_sequence_id(
        client,
        name="Replace steps",
        steps=[_step(subject="first", delay=0), _step(subject="second", delay=10)],
    )
    r = await client.put(
        f"/api/sequences/{sid}",
        json={"name": "Replace steps", "steps": [_step(subject="only", delay=0)]},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["steps"]) == 1
    assert data["steps"][0]["subject"] == "only"
    assert data["steps"][0]["delay"] == 0


@pytest.mark.asyncio
async def test_create_empty_steps_422(client: AsyncClient) -> None:
    r = await client.post(
        "/api/sequences",
        json={"name": "Bad", "steps": []},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_first_step_delay_nonzero_400(client: AsyncClient) -> None:
    r = await client.post(
        "/api/sequences",
        json={
            "name": "Bad",
            "steps": [
                _step(delay=5),
                _step(subject="b", delay=0),
            ],
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "INVALID_SEQUENCE_DATA"


@pytest.mark.asyncio
async def test_invalid_status_transition_409(client: AsyncClient) -> None:
    sid = await _create_sequence_id(client, name="Draft only")
    r = await client.put(f"/api/sequences/{sid}/status", json={"status": "paused"})
    assert r.status_code == 409
    assert r.json()["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_status_change_via_put_sequence_endpoint(client: AsyncClient) -> None:
    sid = await _create_sequence_id(client, name="Status via put")
    r = await client.put(f"/api/sequences/{sid}", json={"status": "active"})
    assert r.status_code == 200
    assert r.json()["status"] == "active"


@pytest.mark.asyncio
async def test_lifecycle_then_terminal_reject(client: AsyncClient) -> None:
    sid = await _create_sequence_id(client, name="Life")

    for status in ("active", "paused", "active", "paused", "archived"):
        r = await client.put(f"/api/sequences/{sid}/status", json={"status": status})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == status

    r = await client.put(f"/api/sequences/{sid}/status", json={"status": "active"})
    assert r.status_code == 409
    assert r.json()["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_get_nonexistent_404(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    r = await client.get(f"/api/sequences/{missing}")
    assert r.status_code == 404
    assert r.json()["code"] == "SEQUENCE_NOT_FOUND"
