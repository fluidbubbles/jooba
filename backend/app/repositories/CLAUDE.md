# repositories package context

This file augments parent `CLAUDE.md` files.
Architecture source: `docs/architecture/architecture.md` (Repository Layer).

## Repository-layer rules

- Repositories own all SQL/data access. No business logic, no HTTP concerns.
- Use `self._db` for the `AsyncSession` attribute (consistent naming convention).
- Call `flush()` instead of `commit()` — services own the transaction boundary.
- Must not import from `app.services` or raise service-layer domain exceptions.
- Use centralized enums from `app.models.enums` for query filters and default values.
- Count concrete columns (e.g. `Model.id`), not relationship attributes, in aggregation queries.
- Avoid N+1 patterns — use subqueries or joins instead of per-row loops.

## Established patterns

- Constructor: `__init__(self, db: AsyncSession) -> None`.
- `get_by_id` returns `Model | None` via `scalar_one_or_none()`.
- `get_or_create` returns `tuple[Model, bool]` (entity, is_new).
- `get_or_create` / `create_if_not_exists` must be race-safe (`begin_nested` + unique-constraint recovery) and return `(entity, is_new)` instead of surfacing duplicate-key races.
- Package `__init__.py` re-exports all repository classes via `__all__`.
