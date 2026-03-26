import pytest
from httpx import AsyncClient


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

    @pytest.mark.asyncio
    async def test_enroll_nonexistent_sequence_404(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/sequences/00000000-0000-0000-0000-000000000099/enroll",
            json={"candidates": [{"email": "test@example.com"}]},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "SEQUENCE_NOT_FOUND"


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
    async def test_list_enrollments_404_for_missing_sequence(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/sequences/00000000-0000-0000-0000-000000000099/enrollments"
        )
        assert response.status_code == 404
        assert response.json()["code"] == "SEQUENCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_list_enrollments_with_status_filter(self, client: AsyncClient) -> None:
        seq_id = await _create_active_sequence(client)
        await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [{"email": "a@b.com"}],
        })
        # All enrolled candidates are "active"
        response = await client.get(f"/api/sequences/{seq_id}/enrollments?status=active")
        assert response.status_code == 200
        assert response.json()["total"] == 1

        # No "completed" enrollments
        response = await client.get(f"/api/sequences/{seq_id}/enrollments?status=completed")
        assert response.status_code == 200
        assert response.json()["total"] == 0

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
