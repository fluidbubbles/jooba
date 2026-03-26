# app package context

This file augments parent `CLAUDE.md` files in `/` and `/backend`.
Architecture source: `docs/architecture/architecture.md`.

## Layering contract

- `api/`: HTTP in/out, request validation, error mapping.
- `services/`: business workflows, state transitions, orchestration, transaction boundary.
- `repositories/` (when present): all SQL/data access only.
- `models/`: ORM entities, relationships, enum definitions.
- `schemas/`: request/response contract types.
- `tasks/` (when added): thin async wrappers with retry policy, no business logic.
- `integrations/` (when added): provider adapters (Nylas/OpenAI/mock), no business rules.

## Cross-package architecture rules

- Service methods are the unit of atomic DB work (commit on success, rollback on exception).
- Routes and tasks must both go through services so business rules are enforced everywhere.
- State transitions must be validated, not applied ad hoc.
- Domain exceptions originate in services and are translated to HTTP in API handlers.
- Async task dispatch from services should go through a dispatcher interface.

## Exceptions

- Domain exceptions live in `services/exceptions.py`. All layers (services, repos, API handlers) may import from this module.

## Evolution note

- `architecture.md` describes the target app structure across plans; if a folder is not present yet, follow these boundaries as new code is added.
