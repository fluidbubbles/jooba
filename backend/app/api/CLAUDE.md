# api package context

This file augments parent `CLAUDE.md` files.
Architecture source: `docs/architecture/architecture.md` (Layered Architecture + Error Contract).

## API-layer rules

- Keep route handlers thin: validate input, call one or more service methods, return schema output.
- Do not embed business workflows in route handlers.
- Do not run direct ORM query logic in route handlers when a service/repository exists.
- Do not call provider SDKs (Nylas/OpenAI) or Celery tasks directly from routes.
- Use typed request/response schemas for all non-trivial endpoints.

## Error mapping contract

- Services raise domain exceptions.
- API exception handlers map to HTTP status codes (for example 404/409/503) with stable machine codes.
- Keep response shape consistent: `{"error": "Human-readable message", "code": "MACHINE_CODE"}`.
- Services must not return HTTP-specific objects.

## Dependency injection expectations

- Use `Depends()` to inject DB sessions and services.
- In webhook endpoints, keep API concerns in API layer (signature/auth checks, payload extraction) before delegating to service methods.
- **Nylas webhook challenge must return plain text:** The `GET /api/nylas/webhook` endpoint must return `PlainTextResponse(challenge)`, not a JSON dict. Nylas rejects JSON challenge responses silently.
