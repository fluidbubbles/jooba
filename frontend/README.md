# Jooba — Frontend

React 19 + TypeScript + Vite + Tailwind CSS v4 + react-router-dom. App shell and routes for the recruiter outreach UI; API calls go through `/api` (proxied to the FastAPI backend).

## Scripts

| Command | Purpose |
|--------|---------|
| `npm run dev` | Vite dev server (default `http://localhost:5173`) |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Preview production build |
| `npm run lint` | ESLint |

## Backend proxy

Vite proxies `/api` and `/health` to the API base URL:

- **Docker Compose:** set `VITE_DEV_PROXY_TARGET=http://backend:8000` (already set in root `docker-compose.yml` for the `frontend` service).
- **Local dev:** omit it or add `.env.development.local` with `VITE_DEV_PROXY_TARGET=http://localhost:8000` while the API runs on port 8000.

See the repository root [README.md](../README.md) for full stack setup and architecture.
