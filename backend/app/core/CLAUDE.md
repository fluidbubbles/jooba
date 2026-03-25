# core package context

This file augments parent `CLAUDE.md` files.
Architecture source: `docs/architecture/architecture.md` (Dependency Injection + Strategy Pattern).

## Core-layer rules

- Keep this package focused on configuration and infrastructure wiring.
- Avoid domain/business logic in `core/`.
- Keep environment variable names stable and documented.
- Preserve async database URL expectations (`postgresql+asyncpg://...`).

## Architecture-specific guidance

- Provider selection is configuration-driven (email provider and LLM provider strategy).
- Repo-path note: if `architecture.md` shows `app/config.py`, use this repo's actual path `app/core/config.py`.
- Core/bootstrap code should choose concrete integration implementations and inject them into services.
- Keep runtime wiring explicit and swappable for tests (mock providers, sync dispatchers).
- Treat queue/runtime settings as infrastructure concerns here, not in services or routes.
