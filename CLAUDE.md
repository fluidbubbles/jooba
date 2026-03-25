# Jooba — Claude Code context

Take-home: recruiter outreach (sequences, CSV enroll, Nylas, LLM classification). **Authoritative architecture:** `docs/architecture/architecture.md`. This file replaces the old `AGENTS.md` — preferences and workspace facts live here.

## Learned user preferences

- When building prioritized delivery or feature task lists, frame each item as a full-stack vertical slice (UI through API, services, and repositories); acceptance criteria should verify backend behavior and data, not only what appears in the browser.
- Treat `docs/architecture/architecture.md` as the source of truth when product screens or exported mockups disagree; align Pencil designs and mockup PNGs to the architecture rather than the other way around.
- When the user scopes work as “Pencil only,” keep changes in the Pencil / `.pen` workflow and avoid editing application frontend code unless they expand the scope.

## Learned workspace facts

- Primary architecture spec: `docs/architecture/architecture.md`. Mockup screenshots: `docs/screenshots/mockups/`. Superpowers plans/specs live under `docs/superpowers/`; high-level phase summaries under `docs/summaries/`.
- Product UI design file in the repo: `pencil-new.pen` at the project root; use Pencil MCP tools for `.pen` design work when the editor encrypts or gates file access.

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
backend/app/          # FastAPI app — main.py, core/config, database, models, api/
backend/alembic/      # Migrations (async env uses settings.database_url)
frontend/src/         # React — components/, pages/, lib/api.ts
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

## Optional local overrides

Use **`.claude.local.md`** at repo root for personal notes (gitignore it if sharing the repo).
