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
- All API response types live in `src/lib/types.ts` — single source for frontend/backend contract alignment.
- Use `ApiRequestError` from `src/lib/api.ts` for typed error handling in catch blocks.
- Always add `console.error` as the first line in every catch block before setting UI error state.
- For async table/list fetches, ignore stale responses (request token/ref or abort) before applying `setState`.
- Modal dialogs must trap focus, restore previous focus on close, and exclude hidden inputs from tabbable selectors.
- Components use `export default function ComponentName` — no named exports for components.
