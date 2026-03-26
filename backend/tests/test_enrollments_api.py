import asyncio

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
        assert body["skipped"] == 0
        assert body["total"] == 1

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

    @pytest.mark.asyncio
    async def test_concurrent_enroll_same_candidate_is_idempotent(
        self, client: AsyncClient
    ) -> None:
        seq_id = await _create_active_sequence(client)
        payload = {"candidates": [{"email": "race@example.com"}]}

        responses = await asyncio.gather(
            client.post(f"/api/sequences/{seq_id}/enroll", json=payload),
            client.post(f"/api/sequences/{seq_id}/enroll", json=payload),
        )

        assert all(response.status_code == 201 for response in responses)
        enrolled_counts = sorted(response.json()["enrolled"] for response in responses)
        skipped_counts = sorted(response.json()["skipped"] for response in responses)
        assert enrolled_counts == [0, 1]
        assert skipped_counts == [0, 1]

        list_response = await client.get(f"/api/sequences/{seq_id}/enrollments")
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1


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
    async def test_candidate_name_falls_back_to_email_local_part(
        self, client: AsyncClient
    ) -> None:
        seq_id = await _create_active_sequence(client)
        await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [{"email": "noname@example.com"}],
        })
        response = await client.get(f"/api/sequences/{seq_id}/enrollments")
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["candidate_name"] == "noname"
        assert item["candidate_email"] == "noname@example.com"

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
    async def test_list_enrollments_status_all_matches_unfiltered(
        self, client: AsyncClient
    ) -> None:
        seq_id = await _create_active_sequence(client)
        await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [{"email": "all@test.com"}],
        })

        unfiltered_response = await client.get(f"/api/sequences/{seq_id}/enrollments")
        all_response = await client.get(f"/api/sequences/{seq_id}/enrollments?status=all")

        assert unfiltered_response.status_code == 200
        assert all_response.status_code == 200
        assert all_response.json() == unfiltered_response.json()

    @pytest.mark.asyncio
    async def test_list_enrollments_limit_offset_paginates_items_only(
        self, client: AsyncClient
    ) -> None:
        seq_id = await _create_active_sequence(client)
        await client.post(f"/api/sequences/{seq_id}/enroll", json={
            "candidates": [
                {"email": "page1@test.com"},
                {"email": "page2@test.com"},
                {"email": "page3@test.com"},
            ],
        })

        response = await client.get(
            f"/api/sequences/{seq_id}/enrollments?status=all&limit=1&offset=1"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_enrollments_rejects_invalid_status_filter(
        self, client: AsyncClient
    ) -> None:
        seq_id = await _create_active_sequence(client)
        response = await client.get(
            f"/api/sequences/{seq_id}/enrollments?status=not-a-status"
        )
        assert response.status_code == 422

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
        assert response.json()["code"] == "SEQUENCE_NOT_FOUND"
