import uuid

import pytest
from httpx import AsyncClient


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
async def test_put_sequence_rejects_status_field(client: AsyncClient) -> None:
    """Status changes must go through PUT /{id}/status, not the general PUT."""
    sid = await _create_sequence_id(client, name="Status via put")
    r = await client.put(f"/api/sequences/{sid}", json={"status": "active"})
    assert r.status_code == 422  # extra="forbid" rejects unknown field


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
async def test_get_sequence_detail_success(client: AsyncClient) -> None:
    sid = await _create_sequence_id(
        client,
        name="Detail Test",
        steps=[_step(subject="First"), _step(subject="Second", delay=60)],
    )
    r = await client.get(f"/api/sequences/{sid}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == sid
    assert data["name"] == "Detail Test"
    assert data["status"] == "draft"
    assert len(data["steps"]) == 2
    assert data["steps"][0]["subject"] == "First"
    assert data["steps"][0]["delay"] == 0
    assert data["steps"][1]["subject"] == "Second"
    assert data["steps"][0]["step_order"] == 0
    assert data["steps"][1]["step_order"] == 1
    assert data["steps"][1]["delay"] == 60
    assert data["role_title"] is None
    assert data["company"] is None
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_nonexistent_404(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    r = await client.get(f"/api/sequences/{missing}")
    assert r.status_code == 404
    assert r.json()["code"] == "SEQUENCE_NOT_FOUND"
