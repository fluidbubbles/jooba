# Plan 5 PR Review Fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix remaining PR review findings from the 6-agent review of Plan 5 (Reply Capture + Inbox).

**Architecture:** Schema enum typing, exception handler registration, detail panel error state, input validation, comment cleanup, and service-layer unit tests.

**Tech Stack:** FastAPI, Pydantic v2, Python 3.13, React 19, TypeScript

---

## File Map

### Backend (modified files)
| File | Changes |
|------|---------|
| `backend/app/schemas/email_event.py` | Use `Sentiment`/`EmailDirection` enums, add `min_length`/`ge` constraints |
| `backend/app/api/exception_handlers.py` | Add `TransientError`/`PermanentError` handlers (503/502) |
| `backend/app/services/exceptions.py` | Add `EmailEventNotFound` typed exception |
| `backend/app/services/email_service.py` | Use `EmailEventNotFound` instead of bare `DomainError` |
| `backend/app/repositories/email_event_repo.py` | Fix `find_by_thread_id` docstring |
| `backend/tests/test_classification_service.py` | New: unit tests for ClassificationService |
| `backend/tests/test_email_service.py` | New: unit tests for EmailService |

### Frontend (modified files)
| File | Changes |
|------|---------|
| `frontend/src/pages/InboxPage.tsx` | Add `detailError` state with retry |

---

### Task 1: Use enum types in Pydantic schemas

**Files:**
- Modify: `backend/app/schemas/email_event.py`

- [ ] **Step 1: Update schema fields to use enums and add constraints**

```python
# backend/app/schemas/email_event.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EmailDirection, Sentiment


class InboxReplyItem(BaseModel):
    id: str
    enrollment_id: str
    candidate_name: str
    candidate_email: str
    body_snippet: str
    sentiment: Sentiment | None
    sentiment_reasoning: str | None
    sequence_name: str
    created_at: datetime
    is_unreplied: bool = False


class ThreadEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    direction: EmailDirection
    subject: str | None
    body_html: str | None
    body_text: str | None
    sentiment: Sentiment | None
    sentiment_reasoning: str | None
    is_manual_reply: bool
    step_index: int | None
    created_at: datetime


class ReplyDetail(BaseModel):
    enrollment_id: str
    candidate_name: str
    candidate_email: str
    sequence_name: str
    sentiment: Sentiment | None
    sentiment_reasoning: str | None
    thread: list[ThreadEvent]


class ManualReplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_html: str = Field(min_length=1)


class SentimentCounts(BaseModel):
    all: int = Field(default=0, ge=0)
    interested: int = Field(default=0, ge=0)
    not_interested: int = Field(default=0, ge=0)
    referral: int = Field(default=0, ge=0)
    neutral: int = Field(default=0, ge=0)
```

- [ ] **Step 2: Run tests to verify no breakage**

Run: `docker compose exec -e TEST_DATABASE_URL=... backend python -m pytest tests/ -q`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/email_event.py
git commit -m "fix: use enum types in inbox schemas, add input constraints"
```

---

### Task 2: Add TransientError/PermanentError exception handlers

**Files:**
- Modify: `backend/app/api/exception_handlers.py`
- Modify: `backend/app/services/exceptions.py`
- Modify: `backend/app/services/email_service.py`

- [ ] **Step 1: Add `EmailEventNotFound` to exceptions.py**

```python
# Add to backend/app/services/exceptions.py
class EmailEventNotFound(DomainError):
    def __init__(self, event_id: str | UUID) -> None:
        super().__init__(f"Email event not found: {event_id}", "EMAIL_EVENT_NOT_FOUND")
```

- [ ] **Step 2: Add exception handlers for TransientError and PermanentError**

Add to `register_exception_handlers` in `backend/app/api/exception_handlers.py`:

```python
from app.services.exceptions import (
    ...,
    PermanentError,
    TransientError,
)

@app.exception_handler(TransientError)
async def transient_error(
    _request: Request, exc: TransientError
) -> JSONResponse:
    return _domain_error_response(exc, 503)

@app.exception_handler(PermanentError)
async def permanent_error(
    _request: Request, exc: PermanentError
) -> JSONResponse:
    return _domain_error_response(exc, 502)
```

**Important:** These must be registered BEFORE the generic `DomainError` handler since `TransientError` and `PermanentError` are subclasses. FastAPI matches most-specific first regardless of registration order, but keeping them grouped above the base handler is clearer.

- [ ] **Step 3: Use `EmailEventNotFound` in email_service.py**

In `backend/app/services/email_service.py`, replace:
```python
raise DomainError("Email event not found", "EMAIL_EVENT_NOT_FOUND")
```
with:
```python
raise EmailEventNotFound(email_event_id)
```
And add the import at the top. This makes it map to 404 via the existing `DomainError` handler (the code is the same).

Actually, we need to register `EmailEventNotFound` as a 404 handler too. Add:
```python
@app.exception_handler(EmailEventNotFound)
async def email_event_not_found(
    _request: Request, exc: EmailEventNotFound
) -> JSONResponse:
    return _domain_error_response(exc, 404)
```

- [ ] **Step 4: Run tests**

Run: `docker compose exec -e TEST_DATABASE_URL=... backend python -m pytest tests/ -q`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/exception_handlers.py backend/app/services/exceptions.py backend/app/services/email_service.py
git commit -m "fix: add TransientError/PermanentError/EmailEventNotFound exception handlers"
```

---

### Task 3: Add detail panel error state in InboxPage

**Files:**
- Modify: `frontend/src/pages/InboxPage.tsx`

- [ ] **Step 1: Add `detailError` state and error UI**

Add state:
```typescript
const [detailError, setDetailError] = useState<string | null>(null)
```

Update `fetchDetail`:
```typescript
const fetchDetail = useCallback((id: string) => {
  const token = ++detailTokenRef.current
  setDetailError(null)
  api.inbox.detail(id).then((data) => {
    if (detailTokenRef.current !== token) return
    setDetail(data)
  }).catch((err) => {
    console.error('Failed to load reply detail', err)
    if (detailTokenRef.current === token) {
      setDetailError('Failed to load thread. Click to retry.')
    }
  })
}, [])
```

Update the detail panel "Select a reply" fallback to also show errors:
```tsx
) : detailError ? (
  <div className="flex flex-col items-center justify-center h-full gap-2">
    <p className="text-red-400 text-sm">{detailError}</p>
    <button
      onClick={() => selectedId && fetchDetail(selectedId)}
      className="text-blue-400 text-sm hover:underline"
    >
      Retry
    </button>
  </div>
) : (
  <div className="flex items-center justify-center h-full text-gray-500 text-sm">
    Select a reply to view the thread
  </div>
)
```

- [ ] **Step 2: Verify TypeScript builds**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/InboxPage.tsx
git commit -m "fix: add detail panel error state with retry in InboxPage"
```

---

### Task 4: Fix stale comments

**Files:**
- Modify: `backend/app/services/email_service.py`
- Modify: `backend/app/repositories/email_event_repo.py`

- [ ] **Step 1: Fix comments**

In `email_service.py`, change the webhook dedup comment (line ~57):
```python
# FROM:
# Webhook deduplication (unique constraint on nylas_message_id)
# TO:
# Webhook deduplication: skip if message already recorded
```

In `email_event_repo.py`, fix `find_by_thread_id` docstring:
```python
# FROM:
"""Find any email event in a thread -- used to match inbound to enrollment."""
# TO:
"""Find the most recent email event in a Nylas thread."""
```

In `email_event_repo.py`, fix `find_by_message_id` docstring:
```python
# FROM:
"""Check if we already processed this message (webhook dedup)."""
# TO:
"""Find an email event by its Nylas message ID."""
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/email_service.py backend/app/repositories/email_event_repo.py
git commit -m "fix: correct stale docstrings in email_service and email_event_repo"
```

---

### Task 5: Add ClassificationService unit tests

**Files:**
- Create: `backend/tests/test_classification_service.py`

- [ ] **Step 1: Write tests**

```python
# backend/tests/test_classification_service.py
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.integrations.openai_client import ClassificationResult
from app.models.enums import Sentiment
from app.services.classification_service import ClassificationService


def _build_service():
    service = ClassificationService(db=MagicMock())
    service._event_repo = SimpleNamespace(
        find_by_id=AsyncMock(),
        update_sentiment=AsyncMock(),
    )
    return service


class TestClassify:
    @pytest.mark.asyncio
    async def test_happy_path_classifies_and_persists(self):
        service = _build_service()
        event_id = uuid4()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment=None, body_text="I'd love to chat!", body_html=None,
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult("interested", "detected interest")
            mock_get.return_value = mock_classifier

            await service.classify(event_id)

        service._event_repo.update_sentiment.assert_awaited_once_with(
            event_id, "interested", "detected interest",
        )

    @pytest.mark.asyncio
    async def test_idempotency_skips_already_classified(self):
        service = _build_service()
        event_id = uuid4()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment="interested", body_text="test", body_html=None,
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            await service.classify(event_id)
            mock_get.assert_not_called()

        service._event_repo.update_sentiment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nonexistent_event_returns_early(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = None

        await service.classify(uuid4())

        service._event_repo.update_sentiment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_sentiment_defaults_to_neutral(self):
        service = _build_service()
        event_id = uuid4()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment=None, body_text="some text", body_html=None,
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult("excited", "unknown")
            mock_get.return_value = mock_classifier

            await service.classify(event_id)

        service._event_repo.update_sentiment.assert_awaited_once_with(
            event_id, Sentiment.NEUTRAL.value, "unknown",
        )

    @pytest.mark.asyncio
    async def test_body_text_preferred_over_body_html(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment=None, body_text="plain text", body_html="<p>html</p>",
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult("neutral", "test")
            mock_get.return_value = mock_classifier

            await service.classify(uuid4())

            mock_classifier.classify.assert_called_once_with("plain text")

    @pytest.mark.asyncio
    async def test_falls_back_to_body_html_when_no_text(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment=None, body_text=None, body_html="<p>html</p>",
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult("neutral", "test")
            mock_get.return_value = mock_classifier

            await service.classify(uuid4())

            mock_classifier.classify.assert_called_once_with("<p>html</p>")

    @pytest.mark.asyncio
    async def test_empty_body_passes_empty_string(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            sentiment=None, body_text=None, body_html=None,
        )

        with patch("app.services.classification_service.get_classifier") as mock_get:
            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = ClassificationResult("neutral", "test")
            mock_get.return_value = mock_classifier

            await service.classify(uuid4())

            mock_classifier.classify.assert_called_once_with("")
```

- [ ] **Step 2: Run tests**

Run: `docker compose exec -e TEST_DATABASE_URL=... backend python -m pytest tests/test_classification_service.py -v`

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_classification_service.py
git commit -m "test: add ClassificationService unit tests"
```

---

### Task 6: Add EmailService unit tests

**Files:**
- Create: `backend/tests/test_email_service.py`

- [ ] **Step 1: Write tests**

```python
# backend/tests/test_email_service.py
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.models.enums import EmailDirection, EnrollmentStatus
from app.services.email_service import EmailService
from app.services.exceptions import DomainError, PermanentError


def _build_service():
    db = MagicMock()
    dispatcher = MagicMock()
    service = EmailService(db=db, dispatcher=dispatcher)
    service._event_repo = SimpleNamespace(
        find_by_id=AsyncMock(),
        find_by_message_id=AsyncMock(),
        find_by_thread_id=AsyncMock(),
        create=AsyncMock(),
    )
    service._enrollment_repo = SimpleNamespace(
        get_by_id=AsyncMock(),
        get_latest_by_candidate=AsyncMock(),
        log_transition=AsyncMock(),
    )
    service._candidate_repo = SimpleNamespace(
        get_by_email=AsyncMock(),
        get_by_id=AsyncMock(),
    )
    service._nylas_repo = SimpleNamespace(
        get_first=AsyncMock(),
    )
    return service


class TestProcessWebhook:
    @pytest.mark.asyncio
    async def test_dedup_skips_existing_message(self):
        service = _build_service()
        service._event_repo.find_by_message_id.return_value = SimpleNamespace(id=uuid4())

        await service.process_webhook({
            "message_id": "msg-1", "thread_id": "t-1",
            "sender_email": "a@b.com", "subject": "", "body_html": "", "body_text": "",
        })

        service._event_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_enrollment_match_skips(self):
        service = _build_service()
        service._event_repo.find_by_message_id.return_value = None
        service._event_repo.find_by_thread_id.return_value = None
        service._candidate_repo.get_by_email.return_value = None

        await service.process_webhook({
            "message_id": "msg-1", "thread_id": "t-1",
            "sender_email": "unknown@b.com", "subject": "", "body_html": "", "body_text": "",
        })

        service._event_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inbound_creates_event_and_dispatches(self):
        service = _build_service()
        enrollment = SimpleNamespace(id=uuid4())
        event = SimpleNamespace(id=uuid4())

        service._event_repo.find_by_message_id.return_value = None
        service._event_repo.find_by_thread_id.return_value = SimpleNamespace(enrollment_id=enrollment.id)
        service._enrollment_repo.get_by_id.return_value = enrollment
        service._nylas_repo.get_first.return_value = SimpleNamespace(email="recruiter@co.com")
        service._event_repo.create.return_value = event

        await service.process_webhook({
            "message_id": "msg-1", "thread_id": "t-1",
            "sender_email": "candidate@b.com", "subject": "Re: Hi", "body_html": "<p>Yes!</p>", "body_text": "Yes!",
        })

        service._event_repo.create.assert_awaited_once()
        call_kwargs = service._event_repo.create.call_args[1]
        assert call_kwargs["direction"] == EmailDirection.INBOUND
        assert service._dispatcher.dispatch.call_count == 2

    @pytest.mark.asyncio
    async def test_outbound_records_external_reply(self):
        service = _build_service()
        enrollment = SimpleNamespace(id=uuid4())

        service._event_repo.find_by_message_id.return_value = None
        service._event_repo.find_by_thread_id.return_value = SimpleNamespace(enrollment_id=enrollment.id)
        service._enrollment_repo.get_by_id.return_value = enrollment
        service._nylas_repo.get_first.return_value = SimpleNamespace(email="recruiter@co.com")

        await service.process_webhook({
            "message_id": "msg-1", "thread_id": "t-1",
            "sender_email": "recruiter@co.com", "subject": "Re: Hi", "body_html": "", "body_text": "",
        })

        service._event_repo.create.assert_awaited_once()
        call_kwargs = service._event_repo.create.call_args[1]
        assert call_kwargs["direction"] == EmailDirection.OUTBOUND
        service._dispatcher.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_account_returns_early(self):
        service = _build_service()
        enrollment = SimpleNamespace(id=uuid4())

        service._event_repo.find_by_message_id.return_value = None
        service._event_repo.find_by_thread_id.return_value = SimpleNamespace(enrollment_id=enrollment.id)
        service._enrollment_repo.get_by_id.return_value = enrollment
        service._nylas_repo.get_first.return_value = None

        await service.process_webhook({
            "message_id": "msg-1", "thread_id": "t-1",
            "sender_email": "a@b.com", "subject": "", "body_html": "", "body_text": "",
        })

        service._event_repo.create.assert_not_awaited()


class TestSendManualReply:
    @pytest.mark.asyncio
    async def test_event_not_found_raises(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = None

        with pytest.raises(DomainError, match="Email event not found"):
            await service.send_manual_reply(uuid4(), "<p>Hi</p>")

    @pytest.mark.asyncio
    async def test_no_account_raises_permanent_error(self):
        service = _build_service()
        service._event_repo.find_by_id.return_value = SimpleNamespace(
            enrollment_id=uuid4(), subject="Hi", nylas_message_id="msg-1",
        )
        service._enrollment_repo.get_by_id.return_value = SimpleNamespace(
            id=uuid4(), candidate_id=uuid4(), status=EnrollmentStatus.REPLIED.value,
            unsubscribe_token="tok",
        )
        service._candidate_repo.get_by_id.return_value = SimpleNamespace(email="a@b.com")
        service._nylas_repo.get_first.return_value = None

        with pytest.raises(PermanentError, match="No email account connected"):
            await service.send_manual_reply(uuid4(), "<p>Hi</p>")
```

- [ ] **Step 2: Run tests**

Run: `docker compose exec -e TEST_DATABASE_URL=... backend python -m pytest tests/test_email_service.py -v`

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_email_service.py
git commit -m "test: add EmailService unit tests (process_webhook + send_manual_reply)"
```

---

### Task 7: Document architectural decision and commit

**Files:**
- Already created: `docs/architecture/decisions.md`

- [ ] **Step 1: Commit the decisions doc**

```bash
git add docs/architecture/decisions.md
git commit -m "docs: add ADR-001 webhook task dispatch race condition"
```
