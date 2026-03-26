# Architecture Decisions

## ADR-001: Webhook task dispatch before DB commit (race condition)

**Status:** Accepted (known risk, mitigated)

**Context:**
In `EmailService.process_webhook()`, after creating an inbound `EmailEvent` via `flush()`, two Celery tasks are dispatched immediately (`classify_reply` and `update_enrollment_on_reply`). The DB transaction is not committed until the `get_db()` dependency exits after the route handler returns. This means Celery workers may pick up tasks before the EmailEvent row is visible in the database.

**Risk:**
If a worker processes the task before the webhook transaction commits, `find_by_id(email_event_id)` returns `None`. Both tasks handle this gracefully (log + return early), but the reply state and classification are permanently lost with no retry.

**Current mitigations:**
- Celery task delivery involves a Redis round-trip + worker prefetch, so in practice the webhook transaction commits before the worker starts processing.
- `acks_late=True` on both tasks means unacknowledged tasks are redelivered on worker crash.
- The `update_enrollment_on_reply` task logs at CRITICAL level on exhaustion.

**Why not fix now:**
This is a take-home demo app. The race window is sub-millisecond under normal load. A production fix requires one of these approaches:

**Solution A: Post-commit dispatch hook.**
Return event IDs from the service, dispatch in the route handler after `get_db()` commits. Requires restructuring the `get_db()` dependency or adding a post-commit callback mechanism.

```python
# Route handler pattern:
event_ids = await service.process_webhook(message_data)
# get_db() commits here (after yield)
# Then dispatch in a background task or middleware
```

**Solution B: Task countdown.**
Add `countdown=2` to both dispatch calls, giving the webhook transaction 2 seconds to commit before workers attempt to read the event. Simple but adds latency to all classifications.

```python
self._dispatcher.dispatch(
    "app.tasks.classification.classify_reply",
    str(event.id),
    queue="ai",
    countdown=2,
)
```

**Solution C: Task retry on missing event.**
Change `mark_replied_by_event` and `ClassificationService.classify` to raise an exception (instead of returning early) when the event is not found, so the task retries with backoff. This is the most resilient approach but adds complexity.

**Decision:** Accept the risk for demo scope. Document for future hardening. If moving to production, implement Solution C (retry on missing event) as it handles both the race condition and genuine data integrity issues.

---
