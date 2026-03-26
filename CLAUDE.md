# Jooba — Claude Code context

Take-home: recruiter outreach (sequences, CSV enroll, Nylas, LLM classification). **Authoritative architecture:** `docs/architecture/architecture.md`. Standing preferences and workspace facts are in the sections below; use this file as the project memory for Claude.

## Learned user preferences

- When building prioritized delivery or feature task lists, frame each item as a full-stack vertical slice (UI through API, services, and repositories); acceptance criteria should verify backend behavior and data, not only what appears in the browser.
- Treat `docs/architecture/architecture.md` as the source of truth when product screens or exported mockups disagree; align Pencil designs and mockup PNGs to the architecture rather than the other way around.
- When the user scopes work as “Pencil only,” keep changes in the Pencil / `.pen` workflow and avoid editing application frontend code unless they expand the scope.
- Keep API schemas domain-first and DRY: expose neutral names (for example `delay`) in JSON; keep storage-oriented names (for example `delay_minutes`) on models and in service/repo payloads, not in public request/response shapes; prefer shared schema bases over duplicated create/update shapes when behavior is identical.
- Avoid module-level `__all__` by default; prefer explicit imports unless wildcard re-exports are required.
- For multi-task implementation plans, create/switch to a dedicated feature branch first, execute in strict plan task order, and run code-simplifier plus code-reviewer after each task boundary before moving to the next task.
- When using `/revise-claude-md`, propose concise `CLAUDE.md` diffs first and apply only after explicit user approval.

## Learned workspace facts

- Primary architecture spec: `docs/architecture/architecture.md`. Mockup screenshots: `docs/screenshots/mockups/`. Superpowers plans/specs live under `docs/superpowers/`; high-level phase summaries under `docs/summaries/`.
- Product UI design file in the repo: `pencil-new.pen` at the project root; use Pencil MCP tools for `.pen` design work when the editor encrypts or gates file access.
- Implementation plans: 6 vertical-slice plans in `docs/superpowers/plans/` (Plan 1: infra, Plan 2: sequences, Plan 3: CSV/candidates, Plan 4: email sending, Plan 5: reply/inbox, Plan 6: dashboard/referrals). Each has a corresponding manual test plan (`plan{N}-manual-test.md`).
- Celery queues: 3 queues (`email`, `ai`, `default`). Single worker processes all three in demo (`-Q email,ai,default`).
- Continual-learning incremental index lives at `.cursor/hooks/state/continual-learning-index.json`; transcript source is the Cursor project `agent-transcripts` directory.

## Quick start (full stack)

```bash
docker compose up --build -d
```

| URL | Service |
|-----|---------|
| http://localhost:3000 | React (Vite in Docker) |
| http://localhost:8000/docs | FastAPI |
| http://localhost:8000/health | Health + DB ping |

Optional: copy root `.env.example` → `.env` to override DB/redis URLs (defaults match Compose).

## Layout

```
backend/app/          # FastAPI app — main.py, core/config, database, models/, api/, services/, repositories/, schemas/, utils/
backend/alembic/      # Migrations (async env uses settings.database_url)
frontend/src/         # React — pages/, components/, lib/api.ts + types.ts
docs/architecture/    # System design
docs/superpowers/plans/  # Implementation plans (Plan 1 = infra shell)
pencil-new.pen        # UI design (use Pencil MCP; do not Read raw .pen as text)
```

## Backend

- **Deps:** Poetry + PEP 621 `pyproject.toml`; Docker runs `poetry install --no-root`.
- **DB URL:** Use **`postgresql+asyncpg://...`** (not `postgresql://`) for SQLAlchemy async.
- **Migrations (inside Compose):**

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic revision --autogenerate -m "describe change"
```

- **Lint (host, if Poetry env works):** `cd backend && poetry run ruff check app`

## Frontend

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
npm run build && npm run lint
```

Vite proxies `/api` and `/health` to `VITE_DEV_PROXY_TARGET` (Compose sets `http://backend:8000`). For local API on the host: `.env.development.local` → `VITE_DEV_PROXY_TARGET=http://localhost:8000`.

## Gotchas

- **Redis:** No host port in Compose (avoids conflict with a local Redis on 6379); backend uses `redis:6379` on the internal network.
- **Postgres:** Published as `127.0.0.1:5432:5432` only.
- **README.md** env snippet may show `postgresql://` for DB; backend Settings expect **`+asyncpg`** — align when debugging connection errors.
- **API integration tests:** `tests/test_*_api.py` files need `TEST_DATABASE_URL` (see `backend/CLAUDE.md` for the Compose one-liner and truncate safety flag). Shared fixtures live in `tests/conftest.py`.

## Universal implementation rules

Use these defaults unless the user explicitly overrides. These rules apply to all plans and phases:

- **API/Service/Repository boundaries:** Routes stay thin, services own business rules/state transitions, repositories own DB queries.
- **Repository purity:** Repositories must not import `app.services` or raise service-layer domain exceptions; use `ValueError` (or similar) for invalid persistence arguments and map to `DomainError` in the service when the API must return a stable `code`.
- **Domain exception flow:** Raise typed domain errors from services and map them in API exception handlers with stable `code` values.
- **Frontend API client:** Reuse `apiFetch` in `frontend/src/lib/api.ts`; avoid introducing duplicate request wrappers.
- **`EmptyState` contract:** Keep `EmptyState` as the default export with `icon: LucideIcon` (do not mix competing icon prop APIs).
- **Route replacement rule:** When implementing pages in `frontend/src/App.tsx`, replace placeholder routes instead of adding duplicate paths.
- **Enrollment UI gating rule:** Show CSV upload/enroll actions only when sequence status is `active`; backend rejects enroll attempts for non-active statuses.
- **Sequence step invariant:** First step must always have `delay = 0`; if steps are removed/reordered, normalize before submit.
- **Aggregation query rule:** Count concrete columns (for example `SequenceStep.id`), not relationship attributes; avoid N+1 loops for list counters.
- **Testing rule:** API integration tests must run with an isolated DB dependency override/fixture; service tests should assert behaviors and exception paths, not only constants.
- **Regression test rule:** When a bug or issue is identified, add a regression test that reproduces the failure. Then have subagents try to fix the bug and prove it with a passing test.
- **No inline imports:** All imports must be at the top of the file. Never use inline/local imports inside functions or methods.
- **No `from __future__ import annotations`:** The project targets Python 3.13+. PEP 604 unions (`X | Y`) and forward references work natively. Do not add `from __future__ import annotations`.
- **Service DI:** Services receive repositories via constructor injection. For single-repo services use `Service(repo)`. For multi-repo services (e.g. `EnrollmentService`) the API factory may pass the session and let the service construct its repos internally — but services must still avoid importing SQLAlchemy types in their business logic.
- **No union types for route dispatch:** Do not use `SchemaA | SchemaB` in FastAPI route parameters for implicit dispatch via `isinstance`. Use separate endpoints instead.
- **No dead infrastructure:** Do not add DB columns, service methods, or config fields for features that have no consumer in the current plan. Add them when the consuming code is built.
- **Celery task contract:** Tasks use `asyncio.run()` to call async services. All imports at module top (not inside inner async functions). Tasks know services only — no repo/integration imports in task files.
- **Strategy pattern ABCs (EmailSender, Classifier, TaskDispatcher):** Keep these interfaces; they enable testability and provider swapping. Do not inline `if/else` provider switching into service methods.
- **Unreplied detection is query-based:** No nudge timer columns (`nudge_due_at`, `nudge_dismissed`) or `set_nudge()` methods. Use `email_event_repo.get_unreplied_inbound()` query per architecture Section 5.7.
- **Frontend API helper name:** The shared request function is `apiFetch` (defined in `src/lib/api.ts`). Never introduce `request`, `fetchApi`, or other aliases — all plans must use `apiFetch`.
- **Analytics batch queries:** Dashboard `get_sequence_summaries()` must use batch GROUP BY queries across all sequences, not per-sequence loops (N+1). Applies to any repository aggregation method.

## Package-level CLAUDE.md policy

- Keep local `CLAUDE.md` files in package directories concise and domain-specific.
- Parent `CLAUDE.md` instructions still apply; local files add constraints for that package only.
- **When modifying package files, update that package's `CLAUDE.md` if the change alters contracts, responsibilities, or conventions documented there.**
- Update package files when responsibilities or contracts change in that package.

## Working in package folders

- When working inside a package folder, read the nearest `CLAUDE.md` first, then parent `CLAUDE.md` files up to repo root.
- For backend edits, consult `backend/CLAUDE.md` plus the relevant `backend/app/<package>/CLAUDE.md` (`api`, `core`, `models`, `schemas`, `services`).
- Use package `CLAUDE.md` files for local architecture decisions; use root `CLAUDE.md` for cross-cutting rules.

## Brief note on current setup

- Backend package `CLAUDE.md` files are now aligned to `docs/architecture/architecture.md` by layer:
  - `api`: HTTP boundary + error mapping contract
  - `core`: configuration/DI/provider wiring
  - `models`: relationships/enums/index and constraint intent
  - `schemas`: contract shape vs business-rule split
  - `services`: workflows, transaction boundaries, state machine, dispatcher usage
- This keeps agent guidance local to each package while remaining consistent with root rules.

## Optional local overrides

Use **`.claude.local.md`** at repo root for personal notes (gitignore it if sharing the repo).
