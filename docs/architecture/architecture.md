# Jooba Recruiter Outreach App — Architecture & Data Flow

---

## 1. System Overview

This app is an internal tool for Jooba operators who run automated email outreach campaigns on behalf of client companies. An operator connects a client's Gmail via Nylas, builds email sequences, uploads candidate CSVs, and the system handles sending, follow-ups, reply detection, AI classification, and referral extraction — all automatically.

The architecture follows **Layered Architecture** with **Event-Driven Side Effects** using Celery as the task queue.

---

## 2. High-Level Architecture

```
                          ┌──────────────┐
                          │   React UI   │
                          │ (TypeScript) │
                          └──────┬───────┘
                                 │ HTTP / REST
                                 ▼
                          ┌──────────────┐
                          │   FastAPI     │
                          │  API Layer   │◄──── Nylas Webhooks
                          └──────┬───────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
             ┌───────────┐ ┌─────────┐ ┌──────────┐
             │  Service   │ │ Celery  │ │  Celery  │
             │  Layer     │ │ Worker  │ │  Beat    │
             │(sync logic)│ │(async   │ │(periodic │
             │            │ │ tasks)  │ │ triggers)│
             └─────┬──────┘ └────┬────┘ └────┬─────┘
                   │             │            │
                   ▼             ▼            ▼
             ┌───────────┐ ┌─────────┐ ┌──────────┐
             │Repository │ │ Nylas   │ │ OpenAI   │
             │ Layer     │ │ API     │ │ API      │
             └─────┬─────┘ └─────────┘ └──────────┘
                   │
                   ▼
             ┌───────────┐
             │ Postgres  │
             └───────────┘
                   ▲
                   │
             ┌───────────┐
             │  Redis     │
             │ (Celery    │
             │  broker)   │
             └───────────┘
```

**Seven processes, one codebase:**

| Process | Role | Docker Service |
|---------|------|----------------|
| FastAPI server | Handles HTTP requests from UI + Nylas webhooks | `backend` |
| Celery email worker | Sends emails via Nylas (rate-limited) | `celery-email` |
| Celery AI worker | Runs LLM classification and extraction | `celery-ai` |
| Celery default worker | Fast DB operations (status updates) | `celery-default` |
| Celery beat | Triggers periodic tasks on a schedule | `celery-beat` |
| PostgreSQL | Persistent data storage | `db` |
| Redis | Celery message broker + result backend | `redis` |

The React frontend is a separate service (`frontend`) that only talks to the FastAPI server over REST.

For the demo, a single worker with `-Q email,ai,default` is sufficient.

---

## 3. Layered Architecture

Each layer has exactly one responsibility. No layer skips a level.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  API LAYER (routes)                                         │
│                                                             │
│  Responsibility: HTTP in/out. Validate request, call        │
│  service, return response. No business logic. No SQL.       │
│  No external API calls.                                     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  SERVICE LAYER                                              │
│                                                             │
│  Responsibility: Business rules and orchestration.          │
│  "What happens when a candidate is enrolled?"               │
│  "What are the rules for advancing a sequence step?"        │
│  "Which replies need recruiter attention?"                   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  REPOSITORY LAYER                                           │
│                                                             │
│  Responsibility: Data access. All SQL queries live here.    │
│  One repository per aggregate root (Sequence, Enrollment,   │
│  Candidate, EmailEvent).                                    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  INTEGRATION LAYER                                          │
│                                                             │
│  Responsibility: Wrap external APIs behind clean            │
│  interfaces. Isolate third-party SDK details.               │
│                                                             │
│  - NylasClient: send_email, get_auth_url, exchange_token    │
│  - OpenAIClient: classify_reply, extract_referral_info      │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TASK LAYER (Celery)                                        │
│                                                             │
│  Responsibility: Async invocation + retry policy.           │
│  Thin wrappers that call services. Each task does one       │
│  thing. Built-in retry with backoff on failure.             │
│                                                             │
│  Knows about: Services only                                 │
│  Does NOT know about: Repositories, Integrations,           │
│  FastAPI, HTTP                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| Layer | Responsibility | Knows About | Does NOT Know About |
|-------|---------------|-------------|---------------------|
| API | HTTP in/out, request validation, error mapping | Pydantic schemas, Services | SQLAlchemy, Nylas, OpenAI, Celery |
| Service | Business rules, orchestration, transaction boundary | Repositories, Integration interfaces, Task dispatcher | FastAPI, HTTP, Celery internals |
| Repository | Data access, all SQL queries | SQLAlchemy, DB session | Business rules, external APIs |
| Integration | Wrap external APIs behind clean interfaces | External SDKs (Nylas, OpenAI) | Database, business rules |
| Task | Async invocation + retry policy | Services only | Repositories, Integrations, FastAPI, HTTP |

### Transaction Boundaries

Each service method is one database transaction:

- Opened at service method entry, committed on success, rolled back on exception
- Repository methods participate in the caller's transaction — they do not manage their own commits
- Celery tasks inherit this: one task invocation = one service call = one transaction
- State transition logging happens synchronously inside the same transaction as the state change — never as a separate async task

This means: if `enrollment_service.advance_step()` sends an email, records the event, and updates the enrollment status, all database writes are atomic. If any step fails, they all roll back. (The external Nylas send cannot be rolled back — see Section 4.6 for the send deduplication strategy.)

### Error Response Contract

Services raise domain-specific exceptions. The API layer maps them to HTTP status codes:

| Exception | HTTP Status | When |
|-----------|-------------|------|
| `CandidateNotFound` | 404 | Lookup by ID/email fails |
| `SequenceNotFound` | 404 | Lookup by ID fails |
| `InvalidStateTransition` | 409 Conflict | E.g., trying to activate an already-active sequence |
| `EnrollmentNotActive` | 409 Conflict | Trying to send to a non-active enrollment |
| `ProviderRateLimited` | 503 Service Unavailable | Nylas/OpenAI rate limit (in API context) |
| `ProviderAuthError` | 503 Service Unavailable | Nylas grant revoked |

All error responses follow a consistent shape:

```json
{"error": "Human-readable message", "code": "ENROLLMENT_NOT_ACTIVE"}
```

FastAPI exception handlers in `main.py` map service exceptions to HTTP responses. Services never import or return HTTP concepts.

### Dependency Injection

- **API layer:** FastAPI `Depends()` provides services and DB sessions to route handlers
- **Celery tasks:** Services are instantiated at task execution time with a fresh DB session
- **Services:** Receive repositories and integration clients via constructor injection
- **Testing:** Swap real repos/integrations for mocks via constructor — no monkey-patching needed

This is how the Strategy Pattern (Section 4.4) actually works in practice: the app bootstraps the correct integration implementation based on config, then injects it into services.

**Why this separation matters:**

- **Testability**: Mock the repository layer to test services without a database. Mock integrations to test without hitting Nylas/OpenAI. Tasks are thin wrappers calling services, making them trivially testable — just verify they invoke the right service method with the right args.
- **Swappability**: Replace OpenAI with Anthropic — change one file in integrations. Replace Nylas with SendGrid — same.
- **Readability**: "Where does the enrollment state machine logic live?" Always `services/enrollment_service.py`. Not scattered across 5 route handlers or buried in Celery task files.
- **Safety**: Tasks only call services, so all business rules and transaction boundaries are enforced regardless of whether the entry point is an HTTP request or an async task.

---

## 4. Design Patterns

### 4.1 Repository Pattern

Every database query is isolated in a repository class. Services never import SQLAlchemy.

```
EnrollmentRepository (Plan 3)
├── create(candidate_id, sequence_id, unsubscribe_token, next_send_at) → Enrollment
├── create_if_not_exists(candidate_id, sequence_id, ...) → tuple[Enrollment, bool]
├── get_by_id(id) → Enrollment | None
├── get_by_candidate_and_sequence(candidate_id, sequence_id) → Enrollment | None
├── list_by_sequence(sequence_id, status_filter, limit, offset) → list[dict]
├── count_by_sequence(sequence_id, status_filter) → int
├── get_analytics(sequence_id) → dict[str, int]
└── log_transition(enrollment_id, from_status, to_status, trigger) → None

EnrollmentRepository (Plan 4 additions)
├── get_due_enrollments() → list[Enrollment]     # next_send_at <= now, status = active
├── update_status(id, new_status) → Enrollment
├── set_next_send(id, datetime) → None
└── clear_next_send(id) → None

CandidateRepository
├── get_by_email(email) → Candidate | None
├── get_by_id(candidate_id) → Candidate | None
├── create(email, first_name, last_name, company, title) → Candidate
└── get_or_create(email, **kwargs) → tuple[Candidate, bool]

EmailEventRepository
├── ...
├── get_unreplied_inbound(sentiments, older_than_minutes) → list[EmailEvent]
│   # Inbound replies classified as interested/referral/neutral
│   # with no outbound reply after them, older than threshold
│   # Pure query — no new columns needed
└── ...
```

Repositories participate in the caller's transaction (see Section 3, Transaction Boundaries).

**Benefit**: If the dashboard analytics query is slow, you optimize it in one place — the repository. No service code changes.

### 4.2 Service Layer Pattern

Services own all business rules. A service method reads like a description of what should happen.

**EnrollmentService:**

```
EnrollmentService (Plan 3 — implemented)
├── enroll_candidates(sequence_id, candidates: list[CandidateInput])
│   → validate sequence is active, deduplicate by email,
│     get-or-create candidates, create enrollments,
│     generate unsubscribe tokens, log transitions
│   (receives structured data from API layer, NOT raw CSV)
│
├── list_enrollments(sequence_id, status_filter, limit, offset)
│   → verify sequence exists, query enrollments with pagination
│
├── get_analytics(sequence_id)
│   → verify sequence exists, return aggregated status/sentiment counts

EnrollmentService (Plan 4 additions — email sending + webhooks)
├── advance_step(enrollment_id)
│   → _validate_sendable(enrollment)      — check status == ACTIVE
│   → _compose_email(enrollment)          — template replacement + footer
│   → email_sender.send(composed)         — integration call
│   → _record_email_event(enrollment, result)
│   → _advance_or_complete(enrollment)    — increment step or mark COMPLETED
│   → _log_transition(enrollment, "email_sent")
│
├── mark_replied(enrollment_id)
│   → set status REPLIED, clear next_send_at, log transition
│
├── opt_out(unsubscribe_token)
│   → validate HMAC token, set OPTED_OUT, clear next_send_at, log transition
│
└── set_nudge(enrollment_id, delay_minutes)
    → compute nudge_due_at, save, log transition
```

**EmailService:**

```
EmailService
├── process_webhook(data)
│   → _match_to_enrollment(thread_id, sender_email)
│   → _determine_direction(sender_email, account_email)
│   → if OUTBOUND: _record_external_reply() + _set_nudge_timer()
│   → if INBOUND: _record_inbound() + _dispatch_classification()
│
├── send_manual_reply(email_event_id, body_html, nudge_delay)
│   → load thread context, append unsubscribe footer,
│     send via integration, record event, set nudge timer
│
└── compose(step, candidate)
    → replace {{placeholders}}, append unsubscribe footer
```

### 4.3 State Machine Pattern

Enrollment status transitions are explicit and validated. Not every transition is allowed.

```
Valid transitions:

ACTIVE → REPLIED        (candidate replied)
ACTIVE → COMPLETED      (all steps sent, no reply)
ACTIVE → BOUNCED        (bounce webhook — recipient server rejected)
ACTIVE → PAUSED         (transient send failures after max retries)
ACTIVE → OPTED_OUT      (clicked unsubscribe)

PAUSED → ACTIVE         (recruiter clicks Resume after investigating)

Invalid (raise error):

REPLIED → ACTIVE        (can't un-reply)
COMPLETED → ACTIVE      (can't restart)
OPTED_OUT → anything    (terminal)
BOUNCED → anything      (terminal)
```

The service layer validates transitions before applying them. If code tries an invalid transition, it raises an error rather than silently corrupting state. Terminal states (REPLIED, COMPLETED, OPTED_OUT, BOUNCED) have no outbound transitions — they are final.

### 4.4 Strategy Pattern (Integrations)

External APIs are behind interfaces. The service layer doesn't know or care which provider is behind them.

```
Classifier interface:
├── OpenAIClassifier (production) — calls GPT-4o-mini
└── MockClassifier (testing) — returns deterministic results

Sender interface:
├── NylasSender (production) — sends through connected email account
└── MockSender (testing) — logs emails without sending
```

Swapping providers = changing an environment variable. No code changes.

```python
# config.py
class Settings(BaseSettings):
    email_provider: str = Field(default="nylas")      # nylas | mock
    llm_provider: str = Field(default="openai")        # openai | mock
```

The app bootstraps the correct implementation at startup based on these values. The service layer receives a `Classifier` and `Sender` interface — it never imports `openai` or `nylas` directly.

### 4.5 Observer Pattern (via Celery Tasks)

When something happens (email received, reply classified), the system dispatches Celery tasks instead of handling everything inline. Each task is an independent "observer" that reacts to the event.

```
"Inbound email received" triggers:
├── Task: classify_reply          (calls classification service)
└── Task: update_enrollment       (calls enrollment_service.mark_replied)

"Reply classified as referral" triggers:
└── Task: extract_referral        (calls referral_service.process_referral)
```

Adding a new reaction (e.g., "send Slack notification on interested reply") means adding one new task. Zero changes to existing code.

**Parallel dispatch safety:** `classify_reply` and `update_enrollment_on_reply` run in parallel. This is safe because all downstream classification tasks operate on the `email_event_id`, not the enrollment status. If a future classification category requires keeping the enrollment ACTIVE (not REPLIED), the flow must change to sequential: classify first, then conditionally update.

### 4.6 Concurrency Control

#### Scheduler Claim Pattern

The periodic `send_due_emails` task atomically claims enrollments before dispatching individual send tasks. This prevents overlapping scheduler cycles from dispatching duplicate tasks for the same enrollment.

```sql
UPDATE enrollments
SET next_send_at = NULL
WHERE id IN (
    SELECT id FROM enrollments
    WHERE status = 'active' AND next_send_at <= now()
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
RETURNING id
```

Claimed enrollments have `next_send_at = NULL`, so the next scheduler cycle skips them. If the send task fails, `enrollment_service.advance_step()` sets `next_send_at` back to a retry time. Requires PostgreSQL (`FOR UPDATE SKIP LOCKED`).

#### Send Deduplication

The Nylas API send and the database write cannot be in the same transaction. If the worker crashes after sending but before recording the email event, a retry would send again.

Mitigation: Before calling Nylas, write a `send_attempt` record (enrollment_id, step_index) in the database. On retry, check if an attempt exists for this enrollment+step. If yes, query Nylas for the message (by thread) to confirm delivery before re-sending. This is an edge case (worker crash between external call and DB write) but is documented for implementer awareness.

### 4.7 Centralized Enums

All status and sentiment values are defined in one file: `app/models/enums.py`. Every layer imports from this single source of truth.

```python
class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    REPLIED = "replied"
    COMPLETED = "completed"
    BOUNCED = "bounced"
    OPTED_OUT = "opted_out"
    PAUSED = "paused"

class Sentiment(str, Enum):
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    REFERRAL = "referral"
    NEUTRAL = "neutral"

class SequenceStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"

VALID_TRANSITIONS = {
    EnrollmentStatus.ACTIVE: [
        EnrollmentStatus.REPLIED,
        EnrollmentStatus.COMPLETED,
        EnrollmentStatus.BOUNCED,
        EnrollmentStatus.OPTED_OUT,
        EnrollmentStatus.PAUSED,
    ],
    EnrollmentStatus.PAUSED: [EnrollmentStatus.ACTIVE],
    # All others are terminal — empty list means no outbound transitions
}
```

Adding a new status or sentiment = add it to the enum here. The service layer's state machine validation, the Pydantic schemas, and the frontend filters all derive from these definitions.

### 4.8 Task Dispatcher

Services dispatch async work through a `TaskDispatcher` interface, not by calling Celery tasks directly. This decouples business logic from the task queue implementation.

```python
class TaskDispatcher:
    def dispatch(self, task_name: str, *args, **kwargs) -> None: ...

class CeleryDispatcher(TaskDispatcher):
    """Production — dispatches to Celery queues."""
    def dispatch(self, task_name, *args, **kwargs):
        task = celery_app.tasks[task_name]
        task.delay(*args, **kwargs)

class SyncDispatcher(TaskDispatcher):
    """Testing — executes task function immediately, no queue."""
    def dispatch(self, task_name, *args, **kwargs):
        task_registry[task_name](*args, **kwargs)
```

Services receive a `TaskDispatcher` via constructor injection:

```python
# In email_service.process_webhook():
self.dispatcher.dispatch("classify_reply", email_event_id)
self.dispatcher.dispatch("update_enrollment_on_reply", email_event_id)
```

Replacing Celery with Dramatiq or ARQ = write a new dispatcher implementation (1 file change).

---

## 5. Data Flow: Core Operations

### 5.1 Email Account Connection (Nylas OAuth)

The app is email-provider agnostic. Nylas abstracts Gmail, Outlook, and other providers behind a single API. The UI says "Email Account," not "Gmail."

```
Recruiter clicks "Connect Email"
        │
        ▼
Frontend → GET /api/nylas/auth-url
        │
        ▼
Backend generates Nylas OAuth URL
        │
        ▼
Frontend redirects browser to provider consent screen (Google, Microsoft, etc.)
        │
        ▼
Recruiter grants access → provider redirects to /api/nylas/callback?code=xyz
        │
        ▼
Backend exchanges code for Nylas grant_id via Nylas API
        │
        ▼
Backend saves NylasAccount(grant_id, email, provider) to Postgres
        │
        ▼
Backend registers Nylas webhook for this grant:
  → POST /webhooks { grant_id, triggers: ["message.created"] }
  → Nylas will now POST to our /api/nylas/webhook for every
    new message (inbound AND outbound) in this account
        │
        ▼
Backend redirects browser to frontend /settings with success
        │
        ▼
Frontend shows: "● Connected — recruiter@ramp.com"
```

**Important**: The grant_id is what we use for all future Nylas API calls. It represents persistent access to that email account. We store it, not the OAuth token.

**No inbox import.** When the account connects, we do NOT import existing emails. We only register a webhook for new messages going forward. The app only sees emails related to threads it created. The recruiter's existing inbox is their personal email — we don't touch it.

---

### 5.2 Create Sequence

The recruiter manually creates a sequence by naming it, writing email steps, and setting delays between them. After saving as a draft, they review and activate.

#### 5.2.1 UI Flow

```
Recruiter clicks "Create Sequence"
        │
        ▼
┌─────────────────────────────────────────────────────┐
│                                                     │
│  Create New Sequence                                │
│                                                     │
│  Sequence Name: [                              ]    │
│                                                     │
│  ── Context (optional) ───────────────────────────  │
│  Role Title:     [                              ]   │
│  Company:        [                              ]   │
│                                                     │
│                                                     │
│  ── Steps ─────────────────────────────────────     │
│  Step 1: Subject [                              ]   │
│          Body    [                              ]   │
│          Delay   [ 0 minutes ]                      │
│                                                     │
│  Step 2: Subject [                              ]   │
│          Body    [                              ]   │
│          Delay   [ 4320 minutes (3 days) ]          │
│                                                     │
│  [+ Add Step]                                       │
│                                                     │
│          [Save Draft]  [Save & Activate]            │
│                                                     │
└─────────────────────────────────────────────────────┘
```

The recruiter types the subject and body for each step, sets delays between steps, and optionally fills in context metadata (role title, company) that describe what this sequence is targeting.

#### 5.2.2 Save Flow

```
Recruiter clicks "Save Draft" or "Save & Activate"
        │
        ▼
Frontend → POST /api/sequences
           {
             name, steps: StepInput[],
             role_title, company
           }
        │
        ▼
API Layer: validates request body via Pydantic schema
        │
        ▼
Service Layer: sequence_service.create(data)
  ├── Validates: at least 1 step, step_order is sequential, delays >= 0
  ├── Calls sequence_repo.create(name, status=DRAFT, metadata)
  └── Calls sequence_repo.create_steps(sequence_id, steps[])
        │
        ▼
Repository Layer: inserts into sequences + sequence_steps tables
        │
        ▼
API Layer: returns SequenceResponse to frontend
        │
        ▼
Frontend shows sequence in draft state with "Activate" button
```

Activating is a separate call: `PUT /api/sequences/:id { status: "active" }`. The recruiter reviews emails before they go live.

The sequence metadata (role title, company) is stored on the Sequence record for UI context — it shows what this sequence is targeting.

#### 5.2.3 Sequence Data Model

```
Sequence
├── id, name, status (DRAFT/ACTIVE/PAUSED/ARCHIVED)
├── role_title, company                    ← context metadata (optional)
├── created_at, updated_at
│
├── SequenceStep (many, ordered by step_order)
│   ├── step_order, subject, body_html, delay_minutes
│   └── (the actual email content, written by the recruiter)
│
└── Enrollment (many)
```

---

### 5.3 Enroll Candidates (CSV Upload)

```
Recruiter uploads CSV on sequence detail page
        │
        ▼
Frontend parses CSV client-side, shows preview table
        │
        ▼
Frontend → POST /api/sequences/:id/enroll
           { candidates: [ {email, first_name, last_name, company, title}, ... ] }
           (structured JSON — API layer does NOT receive raw CSV)
        │
        ▼
API Layer: validates request body via Pydantic schema
  └── Passes list[CandidateInput] to service
        │
        ▼
Service Layer: enrollment_service.enroll_candidates(sequence_id, candidates)
  │
  │  (receives structured data, NOT raw CSV — CSV parsing happens
  │   client-side in CsvUploadModal.tsx via Papa Parse)
  │
  ├── Deduplicate by email within the batch
  │
  ├── For each candidate email:
  │   ├── candidate_repo.get_by_email(email)
  │   ├── If not found: candidate_repo.create(email, first_name, ...)
  │   └── If found: use existing candidate record
  │
  ├── For each candidate:
  │   ├── Generate HMAC-signed unsubscribe token
  │   ├── Compute next_send_at:
  │   │   └── Step 0 delay = 0 → next_send_at = now()
  │   ├── enrollment_repo.create(
  │   │     candidate_id, sequence_id, status=ACTIVE,
  │   │     current_step=0, next_send_at, unsubscribe_token
  │   │   )
  │   └── _log_transition(enrollment, null → ACTIVE, trigger="enrolled")
  │
  └── Return: { enrolled: 142, skipped: 8, total: 150 }
        │
        ▼
API Layer: returns enrollment summary to frontend
        │
        ▼
Frontend updates candidate table on sequence detail page

Note: The actual email sending doesn't happen here.
Celery Beat's periodic task picks up these enrollments
when their next_send_at arrives.
```

---

### 5.4 Sending Emails (Scheduler)

This is a **background process**, not triggered by any API call. It has three layers: the scheduler claims work, a thin Celery task applies retry policy, and a service method contains all business logic.

#### The Scheduler Claim Pattern

```
Celery Beat (every 30 seconds)
        │
        ▼
Triggers task: send_due_emails
        │
        ▼
Scheduler atomically claims due enrollments:
  UPDATE enrollments SET next_send_at = NULL
  WHERE ... FOR UPDATE SKIP LOCKED (see Section 4.6)
  → Returns list of claimed enrollment IDs
        │
        ▼
For each claimed enrollment, dispatch: send_sequence_email.delay(enrollment_id)
```

#### The Send Task (Thin Wrapper)

The Celery task contains zero business logic — it calls the service and applies retry policy based on the exception type.

```
send_sequence_email (Celery task):
  try:
      enrollment_service.advance_step(enrollment_id)
  except RateLimitError as e:
      retry with countdown = e.retry_after
  except TransientError:
      retry with exponential backoff (30s, 60s, 120s, 240s, 480s)
      After 5 failures: enrollment_service.mark_paused(enrollment_id)
  except PermanentError:
      enrollment_service.pause_all_for_account(account_id)
```

#### The Service Method (All Business Logic)

All email sending logic lives in `enrollment_service.advance_step()`. Each sub-step is a private method, making the flow readable and testable.

```
enrollment_service.advance_step(enrollment_id):
  │
  ├── enrollment = enrollment_repo.get_by_id(enrollment_id)
  │   (simple lookup — claim pattern provides exclusivity)
  │
  ├── _validate_sendable(enrollment)
  │   Check status == ACTIVE. If not, return early (idempotency guard).
  │
  ├── composed = _compose_email(enrollment)
  │   Load sequence step, candidate data
  │   Replace {{first_name}}, {{company}}, etc.
  │   Append unsubscribe footer with enrollment's token URL
  │
  ├── result = email_sender.send(composed)
  │   Calls integration (NylasSender)
  │   grant_id, to, subject, body_html, reply_to_message_id
  │
  ├── _record_email_event(enrollment, result)
  │   email_event_repo.create(enrollment_id, direction=OUTBOUND,
  │   step_index, subject, body, nylas_message_id, nylas_thread_id)
  │
  ├── _advance_or_complete(enrollment)
  │   If more steps: enrollment.current_step += 1,
  │                  enrollment.next_send_at = now() + next_step.delay_minutes
  │   If last step: enrollment.status = COMPLETED,
  │                 enrollment.next_send_at = null
  │
  └── _log_transition(enrollment, "email_sent")
      Synchronous write in same transaction.
```

#### Error Handling Taxonomy

Services raise domain exceptions. The task layer catches them and applies retry policy.

| Error Type | Exception | Task Behavior | Enrollment Impact |
|---|---|---|---|
| Rate limit (429) | `RateLimitError` | Retry with `countdown = e.retry_after`. No max retry cap — rate limits always resolve. | No status change |
| Transient (5xx, timeout) | `TransientError` | Exponential backoff: 30s, 60s, 120s, 240s, 480s. Max 5 retries. | After 5 failures: PAUSED (recruiter can investigate + resume) |
| Auth revoked | `PermanentError` | No retry — it won't fix itself | Pause ALL enrollments for this account. Surface in Settings: "Email disconnected — please reconnect" |
| Bounce | (via Nylas webhook, not send task) | N/A — handled by webhook flow | BOUNCED. This is the ONLY path to BOUNCED — never set from a send failure, only from a bounce webhook (recipient server rejected). |

#### Proactive Rate Limit Prevention

```
Token bucket in scheduler: max 40 sends/minute (Nylas free = ~50/min)
Scheduler batches with 60s pause between chunks of 40
```

**Why individual tasks per enrollment**: If sending to candidate #45 fails, it doesn't block candidates #46-150. Each send is isolated. Celery handles retries per task.

---

### 5.5 Message Detection, Filtering + Classification

Nylas fires a webhook for **every new message** in the connected account — inbound and outbound, regardless of source. This includes candidate replies, the recruiter's own replies from their email client, newsletters, personal emails, and spam. Our webhook handler filters the noise.

The `process_webhook()` method is decomposed into private methods that each handle one concern:

```
Any new message appears in recruiter's mailbox
        │
        ▼
Nylas detects it and fires webhook → POST /api/nylas/webhook
        │
        ▼
API Layer:
  ├── Validate webhook signature (security)
  ├── Extract: sender_email, thread_id, body, message_id
  └── Call email_service.process_webhook(data)
        │
        ▼
Service Layer: email_service.process_webhook(data)
  │
  ├── enrollment = _match_to_enrollment(thread_id, sender_email)
  │   ├── Try 1: email_event_repo.find_by_thread_id(thread_id)
  │   │   → finds an outbound email we sent in the same thread
  │   │   → gets enrollment_id from that email event
  │   ├── Try 2 (fallback): candidate_repo.find_by_email(sender_email)
  │   │   → finds candidate → finds active enrollment
  │   └── If no match on either: return None
  │       (this is a non-candidate email — newsletter, personal, spam)
  │
  ├── If enrollment is None: DISCARD silently, return 200
  │
  ├── direction = _determine_direction(sender_email, account_email)
  │   ├── If sender_email == connected_account.email:
  │   │   → direction = OUTBOUND (recruiter sent from email client)
  │   └── Else:
  │       → direction = INBOUND (candidate reply)
  │
  ├── If OUTBOUND:
  │   → _record_external_reply(enrollment, data)
  │   → _set_nudge_timer(enrollment) via enrollment_service.set_nudge()
  │   → DONE (do NOT classify — it's not a candidate reply)
  │
  ├── If INBOUND:
  │   ├── _record_inbound(enrollment, data)
  │   │   email_event_repo.create(
  │   │     enrollment_id, direction=INBOUND,
  │   │     subject, body_html, body_text,
  │   │     nylas_message_id, nylas_thread_id
  │   │   )
  │   │
  │   └── _dispatch_classification(email_event_id, enrollment_id)
  │       ├── self.dispatcher.dispatch("classify_reply", email_event_id)
  │       └── self.dispatcher.dispatch("update_enrollment_on_reply", email_event_id)
  │
  └── Return 200 to Nylas immediately (webhook must respond fast)
```

**Parallel dispatch safety:** `classify_reply` and `update_enrollment_on_reply` run in parallel. This is safe because all downstream classification tasks operate on the `email_event_id`, not the enrollment status. See Section 4.5 for details. If a future classification category requires keeping the enrollment ACTIVE (not REPLIED), the flow must change to sequential: classify first, then conditionally update.

**Why this works for all scenarios:**

| Message type | thread_id match? | sender match? | Action |
|---|---|---|---|
| Candidate replies to outreach | Yes | Yes (candidate) | Process: classify, update enrollment |
| Recruiter replies from email client | Yes | Yes (recruiter) | Record as external outbound, set nudge timer |
| Recruiter replies from app | Yes | Yes (recruiter) | Already recorded by send_manual_reply, webhook deduped by message_id |
| Random email (mom, newsletter, spam) | No | No | Discard silently |
| Candidate emails recruiter outside a thread | No | Maybe | Fallback sender match catches known candidates |

**The thread chain is never broken.** Whether the recruiter replies from the app or from their email client, the message is in the same thread. Nylas sees both. The candidate's next reply is always captured because we're matching on thread_id, not on how the previous message was sent.

#### Parallel Celery Tasks (dispatched by `_dispatch_classification`)

```
        ├──→ Task: update_enrollment_on_reply
        │      ├── enrollment_service.mark_replied(enrollment_id)
        │      │   ├── enrollment.status = REPLIED
        │      │   ├── enrollment.next_send_at = null (cancel follow-ups)
        │      │   └── Log transition: ACTIVE → REPLIED, trigger="reply_received"
        │      └── Done
        │
        └──→ Task: classify_reply
               ├── openai_client.classify(email_body_text)
               │   → sends prompt to GPT-4o-mini with reply text
               │   → returns: { sentiment, reasoning }
               │
               ├── email_event_repo.update_sentiment(
               │     email_event_id, sentiment, reasoning
               │   )
               │
               └── Dispatch downstream tasks based on classification:
                   │
                   ├── If INTERESTED:
                   │   └── (no additional task — it's visible in UI immediately)
                   │
                   ├── If NOT_INTERESTED:
                   │   └── (no additional task — logged and shown in UI)
                   │
                   ├── If REFERRAL:
                   │   └── self.dispatcher.dispatch("extract_referral", email_event_id)
                   │       ├── openai_client.extract_referral(email_body)
                   │       │   → { referred_email, referred_name, referred_title }
                   │       ├── candidate_repo.get_or_create(referred_email, name, title)
                   │       ├── referral_repo.create(referrer, referred, source_email)
                   │       └── (optional) Auto-enroll referred into referral sequence
                   │
                   └── If NEUTRAL:
                       └── (no additional task)
```

**Classification categories:** 4 sentiments — INTERESTED, NOT_INTERESTED, REFERRAL, NEUTRAL (see Section 4.7 for enum definitions).

---

### 5.6 Recruiter Replies From Inbox

```
Recruiter reads candidate reply in Inbox page, types response
        │
        ▼
Frontend → POST /api/replies/:email_event_id/reply
           { body_html, nudge_delay_minutes }
        │
        ▼
API Layer: validates, calls service
        │
        ▼
Service Layer: email_service.send_manual_reply(email_event_id, body_html, nudge_delay)
  │
  ├── Load original email event → get thread_id, enrollment_id
  │
  ├── Append unsubscribe footer to body_html
  │
  ├── nylas_client.send_email(
  │     grant_id, to=candidate.email, body_html,
  │     reply_to_message_id=original_nylas_message_id  (keeps thread)
  │   )
  │
  ├── email_event_repo.create(
  │     enrollment_id, direction=OUTBOUND,
  │     is_manual_reply=True, subject, body_html,
  │     nylas_message_id, nylas_thread_id
  │   )
  │
  ├── enrollment_service.set_nudge(enrollment_id, nudge_delay_minutes)
  │   → compute nudge_due_at = now() + delay_minutes
  │   → save to enrollment, log transition
  │   (nudge logic lives in enrollment_service, NOT inline here)
  │
  └── Log transition: trigger="manual_reply_sent"
        │
        ▼
API Layer: returns success to frontend
        │
        ▼
Frontend: shows sent confirmation, reply appears in thread
```

### 5.7 Unreplied Detection (Query-Based, No Timers)

Instead of timer-based nudges, the system detects unreplied candidates through a simple query on existing data. No new columns, no Celery tasks, no state management.

```
The inbox and dashboard both call:
  email_event_repo.get_unreplied_inbound(
    sentiments=["interested", "referral", "neutral"],
    older_than_minutes=UNREPLIED_THRESHOLD  # env var, default 5
  )

The query:
  SELECT e.* FROM email_events e
  JOIN enrollments en ON e.enrollment_id = en.id
  WHERE e.direction = 'inbound'
    AND e.sentiment IN ('interested', 'referral', 'neutral')
    AND e.created_at < now() - interval :threshold
    AND NOT EXISTS (
        SELECT 1 FROM email_events e2
        WHERE e2.enrollment_id = en.id
          AND e2.direction = 'outbound'
          AND e2.created_at > e.created_at
    )

Returns: interested/referral/neutral replies the recruiter hasn't responded to.
```

**Why this works:**
- NOT_INTERESTED replies are excluded — recruiter intentionally didn't reply
- Once the recruiter replies, the candidate disappears from this list (outbound exists after inbound)
- No timer state to manage, no snooze logic, no dismiss buttons
- Threshold is an env variable: 5 min for demo, 1440 min (24h) for production

**How it surfaces in the UI:**

- **Inbox**: unreplied candidates sort to the top with a "⏳ Unreplied" label
- **Dashboard**: "Interested" stat card shows a secondary line: "3 unreplied" in amber, clicking goes to inbox filtered to unreplied

**Future extensions (v2+, all additive):**
- LLM re-evaluates stale threads: "should we still follow up?"
- Auto-draft follow-up for recruiter to review
- Slack/email notification if unreplied for 2x threshold

---

### 5.8 Unsubscribe

```
Candidate clicks unsubscribe link in email footer:
  https://localhost:8000/api/unsubscribe/{token}
        │
        ▼
API Layer: GET /api/unsubscribe/:token
  │
  ├── Validate HMAC token (prevents enumeration/tampering)
  │
  ├── enrollment_service.opt_out(token)
  │   ├── Find enrollment by unsubscribe_token
  │   ├── enrollment.status = OPTED_OUT
  │   ├── enrollment.next_send_at = null
  │   └── Log transition: → OPTED_OUT, trigger="unsubscribe_clicked"
  │
  └── Return HTML page: "✓ You've been unsubscribed"
        │
        ▼
No further emails sent. Enrollment is in terminal state.
All pending Celery tasks for this enrollment will check
status before executing and skip if OPTED_OUT.
```

---

### 5.9 Dashboard & Analytics

```
Frontend → GET /api/analytics/dashboard
        │
        ▼
Service Layer: analytics_service.get_dashboard()
  │
  ├── analytics_repo.get_aggregate_stats()
  │   → Total candidates, emails sent, replies, interested
  │   → All computed via SQL aggregation, not application-level counting
  │
  ├── analytics_repo.get_sequence_summaries()
  │   → Per-sequence: enrolled, sent, replied, by-sentiment counts
  │   → Single query with GROUP BY, not N+1 queries
  │
  ├── email_event_repo.get_unreplied_inbound(["interested","referral","neutral"], threshold)
  │   → Candidates the recruiter hasn't replied to yet
  │
  ├── Compute attention items:
  │   ├── Unreplied interested/referral/neutral candidates (query-based, no timers)
  │   ├── New referrals
  │   └── Stalled sequences (high send count, zero replies)
  │
  └── Return DashboardStats to API layer
        │
        ▼
API Layer: returns JSON to frontend
        │
        ▼
Frontend renders: stat cards, attention items, sequence table
```

---

## 6. Celery Task Map

### Periodic Tasks (Celery Beat)

| Task | Interval | What it does |
|------|----------|-------------|
| `send_due_emails` | Every 30s | Claims due enrollments via `FOR UPDATE SKIP LOCKED` (Section 4.6), dispatches individual `send_sequence_email` tasks |

### On-Demand Tasks (dispatched by API/services)

| Task | Queue | Triggered by | What it does |
|------|-------|-------------|-------------|
| `send_sequence_email` | `email` | `send_due_emails` | Calls `enrollment_service.advance_step(enrollment_id)`. Handles retry policy per error type. |
| `classify_reply` | `ai` | Webhook handler (via dispatcher) | Calls `classification_service.classify(email_event_id)`. Saves sentiment, dispatches downstream tasks if referral. |
| `extract_referral` | `ai` | `classify_reply` (when referral) | Calls `referral_service.process_referral(email_event_id)`. Extracts referred contact, creates candidate record. |
| `update_enrollment_on_reply` | `default` | Webhook handler (via dispatcher) | Calls `enrollment_service.mark_replied(enrollment_id)`. Sets REPLIED, cancels follow-ups. |

Note: `log_state_transition` is NOT in this table — it's now synchronous inside service methods.

### Queue Strategy

Three queues prevent tasks from blocking each other:

| Queue | Purpose | Why separate |
|-------|---------|-------------|
| `email` | All Nylas send operations | Rate-limited. Don't let classification backlog block sends. |
| `ai` | All LLM calls (classify, extract) | Slow (1-3s). Don't let them clog the email queue. |
| `default` | Fast DB operations (status updates) | Should never be blocked by external API calls. |

**Note for demo:** A single Celery worker processing all three queues (`-Q email,ai,default`) is sufficient for the take-home. Three separate workers is a production optimization for independent scaling.

```yaml
# docker-compose.yml
celery-email:
  command: celery -A app.celery_app worker -Q email -c 4
celery-ai:
  command: celery -A app.celery_app worker -Q ai -c 2
celery-default:
  command: celery -A app.celery_app worker -Q default -c 4
```

### Task Chains

```
Webhook arrives → email_service.process_webhook() dispatches via TaskDispatcher:
  ├── classify_reply(email_event_id)            → ai queue
  │   └── (if referral) → extract_referral      → ai queue
  └── update_enrollment_on_reply(email_event_id) → default queue

These run in parallel. Safe because all downstream tasks operate on email_event_id,
not enrollment status. See Section 4.5 for the safety argument.
```

### Retry Policy

| Task | Error Type | Max Retries | Backoff | On exhaustion |
|------|-----------|-------------|---------|---------------|
| `send_sequence_email` | `RateLimitError` (429) | Unlimited | Retry-After header or exponential (30s, 60s, 120s) | N/A — always resolves |
| `send_sequence_email` | `TransientError` (5xx/timeout) | 5 | Exponential (30s→480s) | `enrollment_service.mark_paused(enrollment_id)` |
| `send_sequence_email` | `PermanentError` (auth revoked) | 0 | None | `enrollment_service.pause_all_for_account(account_id)` + surface in Settings UI |
| `classify_reply` | Any error | 3 | Exponential (10s, 30s, 90s) | Leave sentiment null. Non-critical — recruiter reads the reply. |
| `extract_referral` | Any error | 2 | Fixed 10s | Log warning, skip extraction. Lower priority. |
| `update_enrollment_on_reply` | Any error | 3 | Immediate | Alert — critical failure. Must not lose reply state. |

### Idempotency

Every task's service method checks preconditions before executing:

- `advance_step()`: checks `enrollment.status == ACTIVE`. If status changed (candidate replied between scheduling and execution), returns early without sending.
- `mark_replied()`: checks status is not already REPLIED/OPTED_OUT/BOUNCED. Prevents double processing.
- `classify()`: checks `email_event.sentiment is null`. If already classified (duplicate webhook), skips.

Critical because Celery uses at-least-once delivery. Duplicate task execution will happen at scale. Every service method must be safe to call twice.

### Celery Configuration

Essential settings for production reliability:

| Setting | Value | Why |
|---------|-------|-----|
| `acks_late` | `True` (critical tasks) | Task survives worker crash — redelivered on restart |
| `soft_time_limit` | `60s` (send), `30s` (classify) | Prevents hanging Nylas/OpenAI calls from blocking workers forever |
| `worker_prefetch_multiplier` | `1` | Prevents workers from hoarding tasks with variable execution times |
| `broker_transport_options.visibility_timeout` | `7200` | Prevents Redis from redelivering long-running retry tasks |

**Webhook deduplication:** Add a unique constraint on `email_events.nylas_message_id`. The webhook handler checks for existing events before dispatching tasks. Duplicate webhooks return 200 immediately.

---

## 7. Database Schema Relationships

```
NylasAccount (1)
  │
  │ (used by all outbound email operations)
  │
Sequence (many)
  │
  ├── SequenceStep (many, ordered by step_order)
  │
  └── Enrollment (many)
       │
       ├── belongs to → Candidate (many-to-one)
       │
       ├── EmailEvent (many, ordered by created_at)
       │   │
       │   └── Referral (zero or one, if reply was a referral)
       │
       └── StateTransition (many, ordered by created_at)

Candidate (many)
  │
  └── Enrollment (many — one candidate can be in multiple sequences)
```

**Key indexes for performance:**

| Table | Index | Used by |
|-------|-------|---------|
| enrollments | (status, next_send_at) | Scheduler: find due emails |
| email_events | (enrollment_id, direction, sentiment, created_at) | Unreplied detection query |
| enrollments | (unsubscribe_token) | Unsubscribe endpoint: token lookup |
| email_events | (nylas_thread_id) | Webhook: match reply to enrollment |
| candidates | (email) | CSV upload: deduplication |

**Unique constraints:**

| Table | Constraint | Purpose |
|-------|-----------|---------|
| email_events | (nylas_message_id) | Prevent duplicate webhook processing |
| enrollments | (candidate_id, sequence_id) | Prevent double enrollment |

> **Note:** Status and sentiment enums (and their valid transition map) are defined in `app/models/enums.py`.

---

## 8. File Structure

```
backend/
├── app/
│   ├── main.py                      # FastAPI app, CORS, router mounting
│   ├── celery_app.py                # Celery instance, beat schedule config
│   ├── config.py                    # Environment settings (pydantic-settings)
│   ├── database.py                  # Engine, session factory, Base
│   │
│   ├── models/                      # SQLAlchemy table definitions
│   │   ├── nylas_account.py
│   │   ├── sequence.py              # Sequence + SequenceStep
│   │   ├── candidate.py
│   │   ├── enrollment.py            # Core state machine
│   │   ├── email_event.py
│   │   ├── referral.py
│   │   ├── state_transition.py
│   │   └── enums.py                # Centralized status/sentiment enums + transition map
│   │
│   ├── schemas/                     # Pydantic request/response models
│   │   ├── sequence.py
│   │   ├── candidate.py
│   │   ├── enrollment.py
│   │   ├── email_event.py
│   │   ├── analytics.py
│   │   └── nylas.py
│   │
│   ├── repositories/                # Data access (all SQL here)
│   │   ├── base.py                  # Generic CRUD mixin
│   │   ├── sequence_repo.py
│   │   ├── candidate_repo.py
│   │   ├── enrollment_repo.py       # get_due
│   │   ├── email_event_repo.py      # find_by_thread, create, update_sentiment
│   │   ├── referral_repo.py
│   │   ├── transition_repo.py
│   │   └── analytics_repo.py        # Aggregate queries for dashboard
│   │
│   ├── services/                    # Business logic
│   │   ├── sequence_service.py      # CRUD + activate/pause
│   │   ├── enrollment_service.py    # Enroll, advance, reply, opt-out, nudge
│   │   ├── email_service.py         # Compose, template replace, append footer
│   │   ├── classification_service.py # Orchestrate LLM classification
│   │   ├── referral_service.py      # Extract + create referrals
│   │   └── analytics_service.py     # Dashboard computation
│   │
│   ├── integrations/                # External API wrappers
│   │   ├── nylas_client.py          # OAuth, send, receive
│   │   └── openai_client.py         # Classify, extract referral
│   │
│   ├── tasks/                       # Celery tasks
│   │   ├── email_sending.py         # send_sequence_email
│   │   ├── classification.py        # classify_reply
│   │   ├── enrollment.py            # update_on_reply
│   │   ├── referral.py              # extract_referral
│   │   ├── scheduler.py             # Periodic: send_due
│   │   └── dispatcher.py            # Task dispatcher abstraction (CeleryDispatcher, SyncDispatcher)
│   │
│   ├── api/                         # Route handlers (thin)
│   │   ├── sequences.py             # Sequence CRUD + status transitions
│   │   ├── enrollments.py           # Enroll, list enrollments, analytics
│   │   ├── exception_handlers.py    # Domain error → HTTP mapping
│   │   ├── health.py                # Health check endpoint
│   │   ├── nylas.py                 # OAuth + webhook (Plan 4)
│   │   ├── replies.py               # Inbox + manual reply (Plan 5)
│   │   └── unsubscribe.py           # Public, no auth (Plan 4)
│   │
│   └── utils/
│       ├── unsubscribe.py           # HMAC sign/verify for unsubscribe tokens
│       └── templates.py             # {{placeholder}} replacement logic (Plan 4)
│
├── alembic/                         # Database migrations
├── tests/
├── Dockerfile
├── requirements.txt
└── alembic.ini
```

---

## 9. Production Considerations (README Material)

Things this architecture supports but the take-home doesn't require:

**Multi-tenancy**: Jooba operates for multiple client companies. Adding a `client_id` foreign key to Sequence and NylasAccount scopes everything per client. The layered architecture means this change touches repositories (add WHERE clause) and models (add column) — services and API logic stay the same.

**Multiple Nylas accounts**: Each client connects their own email (Gmail, Outlook, etc.). NylasAccount already supports this — the send task just needs to look up which grant_id to use based on the sequence's client.

**Horizontal scaling**: Celery workers can be scaled independently. If classification is the bottleneck (OpenAI rate limits), add more classification workers. If sending is the bottleneck, add more sending workers. The periodic tasks (beat) remain single-instance.

**Monitoring**: Celery has built-in support for Flower (real-time monitoring dashboard), Prometheus metrics export, and task event streaming. Every task already logs structured data via structlog.

**Post-reply sequences**: The current architecture supports this by adding a second sequence type (post-reply) that gets triggered when recruiter's manual reply goes unanswered. The unreplied detection query already identifies these candidates — upgrading from "surface in inbox" to "automated follow-up" means dispatching a send task based on the same query.