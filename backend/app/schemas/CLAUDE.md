# schemas package context

This file augments parent `CLAUDE.md` files.
Architecture source: `docs/architecture/architecture.md` (Layered Architecture + Data Flows).

## Schema rules

- Keep schemas as API contracts only (request/response shape and basic field constraints).
- Prefer explicit field bounds (`min_length`, `max_length`, `ge`, etc.) for input guardrails.
- Use `model_config = {"from_attributes": True}` for ORM-backed response schemas.
- Keep workflow/state-machine validation in services when it depends on business state.

## Architecture-specific guidance

- API receives structured JSON models, not transport-specific raw payloads (for example CSV parsing should happen before service business logic receives candidate lists).
- Keep request/response names aligned with service entry points used in `architecture.md` flows.
- Use enum-backed fields where possible to prevent drift across API, services, and frontend.
- Reserve machine-readable error codes for exception handlers; schema validation errors remain framework-level 422 responses.
