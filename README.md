# Jooba — Recruiter Outreach Automation

An end-to-end web app that automates recruiter email outreach. Connect an email account, build multi-step sequences, upload candidate CSVs, and let the system handle sending, follow-ups, reply classification, and referral extraction.

## Setup

### 1. Get API keys

| Service | What you need | Where to get it |
|---------|--------------|-----------------|
| Nylas | Client ID + API key | [dashboard.nylas.com](https://dashboard.nylas.com) — create an app, copy credentials |
| OpenAI | API key | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
NYLAS_CLIENT_ID=your-nylas-client-id
NYLAS_API_KEY=your-nylas-api-key
OPENAI_API_KEY=sk-...

# Optional: enable real-time webhooks (requires public URL)
# NYLAS_WEBHOOK_URL=https://your-domain.com/api/nylas/webhook
```

Without `NYLAS_WEBHOOK_URL`, the app falls back to polling Nylas every 5 minutes. With it, webhooks deliver messages in real-time. Polling always runs regardless — it's a fault-tolerance layer that catches any messages webhooks may have missed due to network blips, downtime, or delivery failures. Both paths feed into the same `process_webhook()` pipeline with message-level deduplication, so duplicates are never processed twice. The webhook signing secret is auto-stored in the database when the webhook is registered during OAuth — no manual configuration needed.

> **Faster polling for testing:** The polling interval is set in `backend/app/celery_app.py` under `beat_schedule["poll-nylas-messages"]["schedule"]`. Change `300.0` to `10.0` for 10-second polling, then restart: `docker compose restart celery-beat`

### 3. Start everything

```bash
docker compose up --build -d
docker compose exec backend alembic upgrade head
```

The first command starts all five services (API, frontend, worker, beat scheduler, Postgres, Redis). The second runs database migrations — required on first run and after pulling new code.

| URL | What |
|-----|------|
| http://localhost:3000 | React UI |
| http://localhost:8000/docs | API docs |

> **Note:** For local development without API keys, set `EMAIL_PROVIDER=mock` and `LLM_PROVIDER=mock` in your `backend/.env`. Emails will be logged instead of sent and classification will return dummy results.

### 4. Connect your email

1. Open http://localhost:3000 → Settings
2. Click "Connect Email Account"
3. Complete the Gmail OAuth flow
4. If `NYLAS_WEBHOOK_URL` is set, a webhook is auto-registered with Nylas

### 5. Start sending

1. Create a sequence with email steps
2. Activate the sequence
3. Upload a CSV of candidates (columns: `email`, `first_name`, `last_name`, `company`, `title`)
4. The scheduler picks up due emails every 30 seconds and sends them
5. Replies appear in the Inbox with AI-classified sentiment

## What It Does

1. **Connect email** — Link a Gmail account via Nylas OAuth. The app sends and receives through the recruiter's real inbox.
2. **Build sequences** — Create multi-step email sequences with configurable day delays between steps.
3. **Upload candidates** — CSV upload enrolls candidates into a sequence. The scheduler sends emails automatically.
4. **Reply detection** — Nylas webhooks deliver new messages in real-time. A background poller runs every 5 minutes as a safety net to catch anything webhooks miss. Both paths feed into the same processing pipeline with message-level deduplication. An LLM classifies sentiment (interested / not interested / neutral).
5. **Reply from app** — Recruiters reply directly from the inbox view. Replies thread correctly in Gmail.
6. **Referral extraction** — When a candidate says "talk to X instead," the LLM extracts the referral and creates a new lead.
7. **Dashboard** — Sequence analytics, candidate states, and a "needs follow-up" section for unreplied inbound messages.

## Architecture

```
                              ┌─────────────┐
                              │  React UI   │
                              └──────┬──────┘
                                     │ HTTP
                              ┌──────▼──────┐
                              │ FastAPI API  │◄──── Nylas Webhooks (primary)
                              └──────┬──────┘
                                     │
                              ┌──────▼──────┐
                              │   Services  │──── Business rules, state machine,
                              └──┬───┬───┬──┘     transaction boundaries
                                 │   │   │
                    ┌────────────┘   │   └────────────┐
                    │                │                 │
             ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
             │ Repositories│  │Integrations │  │ Dispatcher  │
             │   (SQL)     │  │(Nylas/OpenAI)│  │  (Celery)  │
             └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
                    │                │                 │
             ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
             │  PostgreSQL │  │ External    │  │   Redis     │
             │             │  │ APIs        │  │  (broker)   │
             └─────────────┘  └─────────────┘  └──────┬──────┘
                                                      │
                                               ┌──────▼──────┐
                                               │Celery Worker│
                                               │  send email │
                                               │  classify   │
                                               │  referrals  │
                                               └─────────────┘
                                               ┌─────────────┐
                                               │ Celery Beat │
                                               │  scheduler  │──── every 30s
                                               │  poller     │──── every 5min
                                               └─────────────┘
```

Five processes, one codebase:

| Process | Role |
|---------|------|
| FastAPI | HTTP API + webhook endpoint |
| Celery worker | Sends emails, classifies sentiment, extracts referrals, polls for missed messages |
| Celery beat | Triggers due email sends (30s) and fallback Nylas polling (5min) |
| PostgreSQL | Persistent storage |
| Redis | Celery message broker |

**Layered architecture** — each layer has one job. API handles HTTP only. Services own business rules. Repositories own all SQL. Integrations wrap external SDKs. Tasks are thin wrappers that call services. No layer skips a level.

## Why This Architecture

This is a take-home project, but I built it with production structure. The patterns here aren't over-engineering — they solve real problems that show up the moment you run async email sending at any scale.

**Concurrency is handled at the database level.** The scheduler claims due enrollments using `FOR UPDATE SKIP LOCKED`. Multiple workers can run simultaneously and never double-send the same email. The DB itself arbitrates who gets the work.

**Failures are expected and tolerated.** Celery tasks use `acks_late=True` so unfinished work is redelivered on crash. A 3-tier retry policy handles transient failures (retry with backoff), rate limits (retry indefinitely), and permanent failures (pause the enrollment for recruiter review). The system degrades gracefully instead of losing emails.

**External APIs never leak into business logic.** Nylas and OpenAI SDK exceptions are caught at the integration boundary and translated into domain errors (`TransientError`, `PermanentError`, `ProviderRateLimited`). Services make decisions based on these domain errors, not raw HTTP status codes. Swapping Nylas for SendGrid or OpenAI for Anthropic is a config change — set `EMAIL_PROVIDER=mock` or `LLM_PROVIDER=mock` and the system runs without any API keys.

**Concerns are separated so changes are local.** Adding a new sequence step type touches the service layer. Fixing a slow query touches one repository. Changing the email provider touches one integration file. Nothing ripples across layers.

**State transitions are explicit.** Enrollment status changes follow a state machine with validated transitions. The service rejects invalid transitions rather than silently corrupting data. Every state change is logged in the same DB transaction as the update.

**Unsubscribe links are stateless.** HMAC-signed tokens — no DB table, no expiry management. The signature proves the token is genuine without a lookup.

## Assumptions & Tradeoffs

- **Single recruiter, no auth.** The spec says "assume a single recruiter user." All endpoints are public. Adding auth is middleware — the architecture supports it without restructuring.
- **Synchronous CSV parsing.** Uploads are processed in one API call. Fine for 50–500 candidates. For 10K+, this would move to a background task with progress tracking.
- **Opt-out is per-enrollment.** Unsubscribing stops one sequence, not all. A production system would add a `do_not_contact` flag on the candidate and check it before every send.
- **Webhook race condition is handled.** Celery tasks are dispatched before the webhook DB transaction commits. If a task runs before the commit, the service raises `EmailEventNotFound`, which triggers the task's retry policy (exponential backoff for classification, immediate retry for enrollment state). The window is sub-millisecond in practice, but the retry ensures correctness under load.
- **No deliverability controls.** No sending limits UI, no SPF/DKIM config, no domain warmup tracking. Important for production but out of scope here.
- **Referral auto-enrollment trusts LLM output.** Extracted referrals surface in the UI for review. A production system would validate that extracted emails appear literally in the reply text before acting on them.

## What I'd Do With More Time

### Next 2–3 days (high impact, low effort)

- **Per-channel rate limiting** — Enforce sending limits per email account to protect sender reputation and avoid provider throttling.
- **Candidate scoring & staged sends** — Candidates arrive pre-scored from Jooba's search. Send to the highest-scored batch first, monitor response rates, then expand to the next tier. This turns every sequence into a natural A/B test — if the top batch doesn't respond, adjust the messaging before reaching the rest.
- **UI polish** — Better experience overall, richer email editor, drag-and-drop sequence builder, sequence forming animations.

### Next 1–2 weeks (high impact, moderate effort)

- **AI sequence generation** — Recruiter provides role context, the LLM generates a full email sequence. The system would ship with a library of proven prompts organized by role type (backend engineer, product manager, etc.) that it selects automatically. Recruiters can also bring their own templates if they prefer.
- **Message effectiveness analysis** — Track which subject lines, tones, and formats get the most replies over time. Surface insights like "shorter first emails get 2x more responses for senior engineers." Basically A/B testing of sequences.
- **Slack/Telegram integration** — Notify recruiters of new replies, interested candidates, or referrals in the channels they already live in.
- **Agentic reply handling** — Pair the state machine with an LLM to handle common low-stakes scenarios autonomously: propose meeting times based on calendar availability, ask clarifying questions when a referral is missing contact info, or confirm details when a candidate's reply is ambiguous. The recruiter stays in the loop for high-stakes decisions (interested candidates, negotiations) but routine back-and-forth happens automatically.

### Longer term (structural changes)

- **Multi-client support** — The current app assumes one recruiter, one inbox. Jooba operates across dozens of client companies. Add a Client model scoping sequences and Nylas accounts, then surface the entire operation as a Kanban board - columns by stage (Enrolled → Contacted → Replied → Interested), cards tagged by client and sequence, so the operator sees pipeline health across all clients at a glance without context-switching.
- **Team features** — Multiple recruiters, shared sequences, per-user analytics.

## Project Structure

```
backend/
  app/
    api/          # Route handlers (HTTP boundary only)
    services/     # Business logic and orchestration
    repositories/ # All database queries
    integrations/ # Nylas, OpenAI SDK wrappers
    tasks/        # Celery task definitions
    models/       # SQLAlchemy models
    schemas/      # Pydantic request/response shapes
    core/         # Config, DB session, dependency injection
  alembic/        # Database migrations
  tests/          # Integration + unit tests

frontend/
  src/
    pages/        # Route-level page components
    components/   # Shared UI components
    lib/          # API client, types, utilities
```
