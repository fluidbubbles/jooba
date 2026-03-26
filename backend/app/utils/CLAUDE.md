# utils package context

This file augments parent `CLAUDE.md` files.

## Utils-layer rules

- Stateless helper functions only — no DB access, no business logic, no service imports.
- May import from `app.core.config` for settings (e.g. secret keys).
- Functions should be pure where possible; side effects limited to reading config.
- This package is a leaf dependency — services and other layers may import from it, but it must not import from them.
