from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.candidate import Candidate
from app.models.enrollment import Enrollment
from app.models.enums import EnrollmentStatus, SequenceStatus
from app.models.sequence import Sequence
from app.utils.unsubscribe import generate_unsubscribe_token


@pytest.mark.asyncio
async def test_unsubscribe_returns_success_page(client: AsyncClient) -> None:
    with patch(
        "app.api.unsubscribe.EnrollmentService.opt_out",
        new=AsyncMock(return_value=True),
    ):
        response = await client.get("/api/unsubscribe/token123")

    assert response.status_code == 200
    assert "You've been unsubscribed" in response.text


@pytest.mark.asyncio
async def test_unsubscribe_returns_invalid_page_for_bad_token(client: AsyncClient) -> None:
    with patch(
        "app.api.unsubscribe.EnrollmentService.opt_out",
        new=AsyncMock(return_value=False),
    ):
        response = await client.get("/api/unsubscribe/token123")

    assert response.status_code == 400
    assert "Invalid unsubscribe link" in response.text


@pytest.mark.asyncio
async def test_unsubscribe_returns_500_page_on_unexpected_error(client: AsyncClient) -> None:
    with patch(
        "app.api.unsubscribe.EnrollmentService.opt_out",
        new=AsyncMock(side_effect=RuntimeError("db unavailable")),
    ):
        response = await client.get("/api/unsubscribe/token123")

    assert response.status_code == 500
    assert "Invalid unsubscribe link" in response.text


@pytest.mark.asyncio
async def test_unsubscribe_updates_enrollment_in_database(
    client: AsyncClient,
    _isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    candidate_id = uuid4()
    sequence_id = uuid4()
    token = generate_unsubscribe_token(candidate_id, sequence_id)
    enrollment_id = uuid4()

    async with _isolated_session_factory() as db:
        db.add(
            Sequence(
                id=sequence_id,
                name="Outbound sequence",
                status=SequenceStatus.ACTIVE.value,
            )
        )
        db.add(
            Candidate(
                id=candidate_id,
                email="candidate@example.com",
            )
        )
        db.add(
            Enrollment(
                id=enrollment_id,
                candidate_id=candidate_id,
                sequence_id=sequence_id,
                status=EnrollmentStatus.ACTIVE.value,
                current_step=0,
                next_send_at=datetime.now(timezone.utc),
                unsubscribe_token=token,
            )
        )
        await db.commit()

    response = await client.get(f"/api/unsubscribe/{token}")
    assert response.status_code == 200

    async with _isolated_session_factory() as db:
        result = await db.execute(select(Enrollment).where(Enrollment.id == enrollment_id))
        enrollment = result.scalar_one()
        assert enrollment.status == EnrollmentStatus.OPTED_OUT.value
        assert enrollment.next_send_at is None
