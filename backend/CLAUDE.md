# Backend package context

This file augments the repo-root `CLAUDE.md`. Follow parent rules first.
Authoritative backend design is `docs/architecture/architecture.md`.

## Scope

- FastAPI backend with layered architecture (non-linear): API routes and task wrappers both call services; services orchestrate repositories and integrations; async side effects are dispatched via the task dispatcher.
- SQLAlchemy async + Alembic migrations + Celery task processing.

## Commands

```bash
poetry run ruff check app
python -m pytest
alembic upgrade head
# From repo root (Compose workflow)
docker compose exec backend alembic upgrade head
```

## Architecture rules from `architecture.md`

- **Layer boundaries:** API handles HTTP/schema mapping only; services own business rules and orchestration; repositories own all SQL; tasks are thin wrappers that call services.
- **Transaction model:** one service method = one transaction; repository methods never commit independently.
- **State logging:** state transition writes happen synchronously in the same transaction as the state change.
- **Error contract:** services raise domain exceptions; API maps them to HTTP with stable code values and shape `{"error": "...", "code": "..."}`.
- **Single source enums:** status/sentiment values are centralized in `app/models/enums.py`.
- **Task decoupling:** services dispatch async work through a dispatcher abstraction, not direct Celery calls.

## Practical guardrails

- Keep DB URL format as `postgresql+asyncpg://...`.
- If implementation differs from docs, align code toward architecture while preserving current working behavior.
- **Integration tests require:** `TEST_DATABASE_URL` env var and `ALLOW_TEST_DB_TRUNCATE=1` for safety. Run via: `docker compose exec -e TEST_DATABASE_URL=postgresql+asyncpg://jooba:jooba@db:5432/jooba -e ALLOW_TEST_DB_TRUNCATE=1 backend python -m pytest tests/test_sequences_api.py -v`
