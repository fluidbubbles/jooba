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

**Five processes, one codebase:**

| Process | Role | Docker Service |
|---------|------|----------------|
| FastAPI server | Handles HTTP requests from UI + Nylas webhooks | `backend` |
| Celery worker | Executes async tasks (classify, send, extract) | `celery-worker` |
| Celery beat | Triggers periodic tasks on a schedule | `celery-beat` |
| PostgreSQL | Persistent data storage | `db` |
| Redis | Celery message broker + result backend | `redis` |

The React frontend is a separate service (`frontend`) that only talks to the FastAPI server over REST.

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
EnrollmentRepository
├── get_by_id(id) → Enrollment
├── get_due_enrollments() → list[Enrollment]     # next_send_at <= now, status = active
├── get_by_sequence(sequence_id) → list[Enrollment]
├── create(candidate_id, sequence_id, ...) → Enrollment
├── update_status(id, new_status) → Enrollment
├── set_next_send(id, datetime) → None
└── clear_next_send(id) → None

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
EnrollmentService
├── enroll_candidates(sequence_id, candidates: list[CandidateInput])
│   → deduplicate by email, get-or-create candidates,
│     create enrollments, generate unsubscribe tokens,
│     compute next_send_at, log transitions
│   (receives structured data from API layer, NOT raw CSV)
│
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
│  About Company:  [                              ]   │
│  Key Selling     [                              ]   │
│  Points:         [                              ]   │
│  Tone:           [ Professional ▼ ]                 │
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

The recruiter types the subject and body for each step, sets delays between steps, and optionally fills in context metadata (role, company, selling points, tone) that describe what this sequence is targeting.

#### 5.2.2 Save Flow

```
Recruiter clicks "Save Draft" or "Save & Activate"
        │
        ▼
Frontend → POST /api/sequences
           {
             name, steps: StepInput[],
             metadata: { role_title, company, about_company,
                         selling_points, tone }
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

The sequence metadata (role, company, selling points, tone) is stored on the Sequence record for UI context — it shows what this sequence is targeting.

#### 5.2.3 Sequence Data Model

```
Sequence
├── id, name, status (DRAFT/ACTIVE/PAUSED/ARCHIVED)
├── role_title, company, about_company     ← context metadata (optional)
├── selling_points, tone                   ← context metadata (optional)
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
Frontend parses CSV client-side, shows preview
        │
        ▼
Frontend → POST /api/sequences/:id/enroll (multipart form with CSV)
        │
        ▼
API Layer: receives file, passes to service
        │
        ▼
Service Layer: enrollment_service.enroll_candidates(sequence_id, csv_data)
  │
  ├── Parse CSV rows into candidate records
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
  │   └── Log state transition: null → ACTIVE, trigger="enrolled"
  │
  └── Return: { enrolled: 142, already_existed: 8, total: 150 }
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

This is a **background process**, not triggered by any API call.

```
Celery Beat (every 30 seconds)
        │
        ▼
Triggers task: send_due_emails
        │
        ▼
Task queries: enrollment_repo.get_due_enrollments()
  → SELECT * FROM enrollments
    WHERE status = 'active'
    AND next_send_at <= now()
    JOIN sequence_steps, candidates, sequences
        │
        ▼
For each due enrollment, dispatch: send_sequence_email.delay(enrollment_id)
        │
        ▼
Individual send task (runs in Celery worker):
  │
  ├── Load enrollment + candidate + sequence step
  │
  ├── email_service.compose(step, candidate)
  │   ├── Replace {{first_name}}, {{company}}, etc. in subject + body
  │   └── Append unsubscribe footer with enrollment's unique token URL
  │
  ├── nylas_client.send_email(
  │     grant_id=nylas_account.grant_id,
  │     to=candidate.email,
  │     subject=composed_subject,
  │     body_html=composed_body,
  │     reply_to_message_id=last_outbound_message_id  (for threading)
  │   )
  │
  ├── email_event_repo.create(
  │     enrollment_id, direction=OUTBOUND,
  │     step_index=current_step, subject, body,
  │     nylas_message_id, nylas_thread_id
  │   )
  │
  ├── Determine next state:
  │   ├── If more steps remain:
  │   │   ├── next_step = sequence.steps[current_step + 1]
  │   │   ├── enrollment.current_step += 1
  │   │   └── enrollment.next_send_at = now() + next_step.delay_minutes
  │   └── If this was the last step:
  │       ├── enrollment.status = COMPLETED
  │       ├── enrollment.next_send_at = null
  │       └── enrollment.completed_at = now()
  │
  └── Log state transition: trigger="email_sent", metadata={step_index}
  
  On failure (error-type determines behavior):
  │
  ├── Rate limit (429):
  │   ├── Read Retry-After header from Nylas response
  │   ├── Celery retry with delay = Retry-After (or exponential: 30s, 60s, 120s)
  │   ├── No max retry cap — rate limits always resolve, just wait
  │   └── Log as transient, do NOT change enrollment status
  │
  ├── Transient error (5xx, timeout, connection error):
  │   ├── Celery retries with exponential backoff (30s, 60s, 120s)
  │   ├── Max 5 retries
  │   └── After 5 failures: mark enrollment PAUSED, log transition
  │       (recruiter can investigate + resume — not data loss)
  │
  ├── Permanent error (invalid grant, auth revoked):
  │   ├── No retry — it won't fix itself
  │   ├── Pause ALL enrollments for this account
  │   └── Surface in Settings: "Email disconnected — please reconnect"
  │
  └── Bounce (Nylas webhook: message.bounce):
      ├── Mark enrollment BOUNCED — this is the ONLY path to BOUNCED
      └── BOUNCED is never set from a send failure, only from a
          bounce webhook (recipient server rejected the email)

  Proactive rate limit prevention:
  ├── Token bucket in scheduler: max 40 sends/minute (Nylas free = ~50/min)
  └── Scheduler batches with 60s pause between chunks of 40
```

**Why individual tasks per enrollment**: If sending to candidate #45 fails, it doesn't block candidates #46-150. Each send is isolated. Celery handles retries per task.

---

### 5.5 Message Detection, Filtering + Classification

Nylas fires a webhook for **every new message** in the connected account — inbound and outbound, regardless of source. This includes candidate replies, the recruiter's own replies from their email client, newsletters, personal emails, and spam. Our webhook handler filters the noise.

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
  ├── STEP 1: Match to a known thread
  │   ├── Try 1: email_event_repo.find_by_thread_id(thread_id)
  │   │   → finds an outbound email we sent in the same thread
  │   │   → gets enrollment_id from that email event
  │   ├── Try 2 (fallback): candidate_repo.find_by_email(sender_email)
  │   │   → finds candidate → finds active enrollment
  │   └── If no match on either: DISCARD silently, return 200
  │       (this is a non-candidate email — newsletter, personal, spam)
  │
  ├── STEP 2: Determine direction
  │   ├── If sender_email == connected_account.email:
  │   │   → This is the RECRUITER sending (from their email client, not the app)
  │   │   → direction = OUTBOUND, source = "external"
  │   │   → Record it so the thread stays complete in our UI
  │   │   → Record it so the thread stays complete in our UI
  │   │   → Do NOT classify (it's not a candidate reply)
  │   │   → DONE
  │   └── Else:
  │       → This is a CANDIDATE replying
  │       → direction = INBOUND, source = "webhook"
  │       → Continue to classification
  │
  ├── STEP 3: Record the inbound message
  │   email_event_repo.create(
  │     enrollment_id, direction=INBOUND,
  │     subject, body_html, body_text,
  │     nylas_message_id, nylas_thread_id
  │   )
  │
  ├── STEP 4: Dispatch async tasks (fire and return fast)
  │   ├── classify_reply.delay(email_event_id)        → queue: ai
  │   └── update_enrollment_on_reply.delay(email_event_id) → queue: default
  │
  └── Return 200 to Nylas immediately (webhook must respond fast)
```

**Why this works for all scenarios:**

| Message type | thread_id match? | sender match? | Action |
|---|---|---|---|
| Candidate replies to outreach | Yes | Yes (candidate) | Process: classify, update enrollment |
| Recruiter replies from email client | Yes | Yes (recruiter) | Record as external outbound (clears unreplied state) |
| Recruiter replies from app | Yes | Yes (recruiter) | Already recorded by send_manual_reply, webhook deduped by message_id |
| Random email (mom, newsletter, spam) | No | No | Discard silently |
| Candidate emails recruiter outside a thread | No | Maybe | Fallback sender match catches known candidates |

**The thread chain is never broken.** Whether the recruiter replies from the app or from their email client, the message is in the same thread. Nylas sees both. The candidate's next reply is always captured because we're matching on thread_id, not on how the previous message was sent.
        │
        ▼
PARALLEL CELERY TASKS:
        │
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
                   │   └── extract_referral.delay(email_event_id)
                   │       ├── openai_client.extract_referral(email_body)
                   │       │   → { referred_email, referred_name, referred_title }
                   │       ├── candidate_repo.get_or_create(referred_email, name, title)
                   │       ├── referral_repo.create(referrer, referred, source_email)
                   │       └── (optional) Auto-enroll referred into referral sequence
                   │
                   └── If NEUTRAL:
                       └── (no additional task)
```

---

### 5.6 Recruiter Replies From Inbox

```
Recruiter reads candidate reply in Inbox page, types response
        │
        ▼
Frontend → POST /api/replies/:email_event_id/reply
           { body_html }
        │
        ▼
API Layer: validates, calls service
        │
        ▼
Service Layer: email_service.send_manual_reply(email_event_id, body_html)
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

### 5.7 Unsubscribe

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
| `send_due_emails` | Every 30s | Finds enrollments where next_send_at <= now, dispatches individual send tasks |

### On-Demand Tasks (dispatched by API/services)

| Task | Queue | Triggered by | What it does |
|------|-------|-------------|-------------|
| `send_sequence_email` | `email` | `send_due_emails` periodic task | Sends one email for one enrollment via Nylas |
| `classify_reply` | `ai` | Nylas webhook handler | Calls LLM to classify reply sentiment |
| `extract_referral` | `ai` | `classify_reply` (when referral) | Calls LLM to extract referred person, creates candidate |
| `update_enrollment_on_reply` | `default` | Nylas webhook handler | Marks enrollment as REPLIED, cancels follow-ups |
| `log_state_transition` | `default` | Various | Writes audit log entry |

### Queue Strategy

Three queues prevent tasks from blocking each other:

| Queue | Purpose | Why separate |
|-------|---------|-------------|
| `email` | All Nylas send operations | Nylas has rate limits. Don't let classification backlog block sends. |
| `ai` | All LLM calls (classify, extract) | LLM calls are slow (1-3s). Don't let them clog the email queue. |
| `default` | Fast DB operations (status updates, logging) | Should never be blocked by external API calls. |

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
Nylas webhook arrives
  ├── classify_reply
  │   └── (if referral) → extract_referral
  └── update_enrollment_on_reply
      └── log_state_transition
```

### Retry Policy

| Task | Max Retries | Backoff | On exhaustion | Why |
|------|-------------|---------|---------------|-----|
| `send_sequence_email` (rate limit 429) | Unlimited | Retry-After header or exponential (30s, 60s, 120s) | N/A — always resolves | Rate limits are transient, never give up |
| `send_sequence_email` (5xx/timeout) | 5 | Exponential (30s, 60s, 120s, 240s, 480s) | PAUSE enrollment (not BOUNCED) | Recruiter can investigate + resume |
| `send_sequence_email` (auth error) | 0 | None | Pause ALL enrollments, flag in Settings | Grant revoked — retrying won't help |
| `classify_reply` | 3 | Exponential (10s, 30s, 90s) | Log warning, leave sentiment null | Non-critical — recruiter can read the reply |
| `extract_referral` | 2 | Fixed 10s | Log warning, skip extraction | Lower priority, can fail gracefully |
| `update_enrollment_on_reply` | 3 | Immediate | Alert — critical failure | Must not lose reply state |

### Idempotency

Every task checks preconditions before executing:

- `send_sequence_email`: checks enrollment.status == ACTIVE before sending. If status changed (e.g., candidate replied between scheduling and execution), task exits without sending.
- `update_enrollment_on_reply`: checks status is not already REPLIED/OPTED_OUT/BOUNCED. Prevents double processing.
- `classify_reply`: checks email_event.sentiment is null. If already classified (duplicate webhook), skips.

This is critical because at scale, duplicate task execution will happen (Celery at-least-once delivery). Every task must be safe to run twice.

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
│   │   └── state_transition.py
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
│   │   ├── enrollment_service.py    # Enroll, advance, reply, opt-out
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
│   │   └── transitions.py           # log_state_transition
│   │
│   ├── api/                         # Route handlers (thin)
│   │   ├── sequences.py
│   │   ├── candidates.py
│   │   ├── enrollments.py
│   │   ├── replies.py
│   │   ├── analytics.py
│   │   ├── nylas.py                 # OAuth + webhook
│   │   └── unsubscribe.py           # Public, no auth
│   │
│   └── utils/
│       ├── tokens.py                # HMAC sign/verify for unsubscribe
│       └── templates.py             # {{placeholder}} replacement logic
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