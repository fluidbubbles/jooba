# services package context

This file augments parent `CLAUDE.md` files.
Architecture source: `docs/architecture/architecture.md` (Service Layer Pattern + State Machine + Task Dispatcher).

## Service-layer rules

- Services own business workflows, invariants, and status-transition enforcement.
- Raise typed domain exceptions for invalid operations and missing resources.
- Keep services orchestration-focused; query mechanics belong in repositories and provider SDK calls belong in integrations implementations.
- Services orchestrate repositories plus integration interfaces, not framework/transport concerns.
- Validate cross-step invariants (for example sequence first-step delay rules) before persistence.
- Log guard-clause early returns at appropriate levels: `DEBUG` for idempotency guards (expected re-delivery), `ERROR` for data integrity issues (missing enrollment/sequence/candidate). Never return silently from a method that processes claimed work.

## Transaction and state requirements

- One service method = one DB transaction boundary.
- Repository calls participate in caller transaction and do not commit on their own.
- State transition logging is synchronous in the same transaction as the state update.
- Explicitly validate allowed transitions; reject invalid transitions with domain errors.

## Async/task integration rules

- Services dispatch background work via dispatcher interface (not direct Celery task imports).
- Task wrappers should call services; business rules must remain in services.
- Service methods called by tasks must be idempotent/precondition-checked for at-least-once delivery semantics.
- **Enrollment completion must increment `current_step`:** When the last step is sent, `current_step` must be set to `step_index + 1` before marking `status=completed`. Otherwise the UI shows "N-1 of N" for completed enrollments.
