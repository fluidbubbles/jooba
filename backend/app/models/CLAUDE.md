# models package context

This file augments parent `CLAUDE.md` files.
Architecture source: `docs/architecture/architecture.md` (Centralized Enums + Schema Relationships).

## Model rules

- Keep SQLAlchemy models as the source of DB shape and relationships.
- Keep relationship names and `back_populates` explicit and symmetric.
- Use centralized enums from `app.models.enums` for persisted status/sentiment values.
- Keep valid transition maps centralized in enums (service layer enforces them).

## Required relationship knowledge

- `Sequence` has many `SequenceStep` and many `Enrollment`.
- `Enrollment` belongs to `Candidate` and has many `EmailEvent` and `StateTransition`.
- `Referral` is associated to an `EmailEvent` when sentiment is referral.

## Index/constraint guidance from architecture

- Preserve scheduler index patterns on enrollments (`status`, `next_send_at`) for due-send lookups.
- Preserve unique constraints for dedup and safety:
  - unique enrollment per `(candidate_id, sequence_id)`
  - unique message ID for inbound event dedup when implemented
- Keep unsubscribe-token and thread-id lookup paths indexed where applicable.
