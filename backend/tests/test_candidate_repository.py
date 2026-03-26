import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.candidate import Candidate
from app.repositories.candidate_repo import CandidateRepository


async def _create_with_repo(
    session_factory: async_sessionmaker[AsyncSession], email: str
) -> tuple[str, bool]:
    async with session_factory() as session:
        repo = CandidateRepository(session)
        candidate, is_new = await repo.get_or_create(email)
        await session.commit()
        return str(candidate.id), is_new


@pytest.mark.asyncio
async def test_get_or_create_normalizes_email_and_is_idempotent(
    _isolated_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _isolated_session_factory() as session:
        repo = CandidateRepository(session)
        candidate_1, is_new_1 = await repo.get_or_create("  Jane@Example.com ")
        candidate_2, is_new_2 = await repo.get_or_create("jane@example.com")

        assert is_new_1 is True
        assert is_new_2 is False
        assert candidate_1.id == candidate_2.id
        assert candidate_1.email == "jane@example.com"


@pytest.mark.asyncio
async def test_get_or_create_handles_concurrent_duplicate_insert_race(
    _isolated_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_get_by_email = CandidateRepository.get_by_email
    first_lookup_calls = 0
    first_lookup_lock = asyncio.Lock()
    lookup_barrier = asyncio.Event()

    async def synchronized_get_by_email(
        self: CandidateRepository, email: str
    ) -> Candidate | None:
        nonlocal first_lookup_calls

        should_wait = False
        async with first_lookup_lock:
            if first_lookup_calls < 2:
                first_lookup_calls += 1
                should_wait = True
                if first_lookup_calls == 2:
                    lookup_barrier.set()

        if should_wait:
            await lookup_barrier.wait()

        return await original_get_by_email(self, email)

    monkeypatch.setattr(
        CandidateRepository,
        "get_by_email",
        synchronized_get_by_email,
    )

    results = await asyncio.gather(
        _create_with_repo(_isolated_session_factory, "race@example.com"),
        _create_with_repo(_isolated_session_factory, "RACE@example.com"),
        return_exceptions=True,
    )

    assert all(not isinstance(result, Exception) for result in results)
    ids = {candidate_id for candidate_id, _ in results}
    assert len(ids) == 1
    assert sorted(is_new for _, is_new in results) == [False, True]

    async with _isolated_session_factory() as session:
        count = await session.scalar(
            select(func.count(Candidate.id)).where(Candidate.email == "race@example.com")
        )
        assert count == 1
