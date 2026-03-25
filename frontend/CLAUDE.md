# Frontend package context

This file augments the repo-root `CLAUDE.md`. Follow parent rules first.

## Scope

- React + TypeScript UI for Jooba recruiter workflows.
- Route shells and pages under `src/pages`, shared UI under `src/components`.

## Commands

```bash
npm run dev
npm run build
npm run lint
```

## Local rules

- Reuse `apiFetch` from `src/lib/api.ts` for network calls.
- Keep `EmptyState` usage aligned with the shared component contract.
- In `src/App.tsx`, replace temporary placeholder routes with real page components (avoid duplicate route paths).
- Keep TS strictness clean (`noUnusedLocals`, `noUnusedParameters`).
