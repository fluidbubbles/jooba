# Jooba — Recruiter Outreach Automation

An end-to-end web app that automates recruiter email outreach: connect an email account, build multi-step sequences, upload candidate CSVs, and let the system handle sending, follow-ups, reply classification, and referral extraction.

## Architecture Overview

**Stack:** Python/FastAPI + TypeScript/React + PostgreSQL + Redis + Docker Compose

**Backend architecture:** Layered (API → Service → Repository → Integration) with event-driven side effects via Celery.

```
React UI → FastAPI API → Service Layer → Repository (Postgres)
                ↑                ↓
          Nylas Webhooks    Celery Workers → Nylas API / OpenAI API
                            Celery Beat (scheduler)
```

Five processes, one codebase:

| Process | Role |
|---------|------|
| FastAPI server | HTTP API + Nylas webhook handler |
| Celery worker | Async tasks (send emails, classify replies, extract referrals) |
| Celery beat | Periodic scheduler (sends due emails every 30s) |
| PostgreSQL | Persistent storage |
| Redis | Celery message broker |

## Design Patterns

### Repository Pattern

All database queries are isolated in repository classes. Services never import SQLAlchemy. This means swapping the database or optimizing a slow query touches one file — no business logic changes.

```
EnrollmentRepository
├── get_due_enrollments()     → scheduler uses this every 30s
├── get_overdue_nudges()      → dashboard "Needs Follow-Up" section
├── get_by_sequence()         → sequence detail candidate table
└── create(), update_status() → all state changes
```

### State Machine Pattern

Enrollment status transitions are explicit and validated. The service layer rejects invalid transitions rather than silently corrupting state.

```
ACTIVE → REPLIED       (candidate replied)
ACTIVE → COMPLETED     (all steps sent, no reply)
ACTIVE → BOUNCED       (email delivery failed)
ACTIVE → OPTED_OUT     (clicked unsubscribe)
ACTIVE → PAUSED        (transient send failures)
PAUSED → ACTIVE        (recruiter resumes after investigation)
```

Terminal states (REPLIED, COMPLETED, BOUNCED, OPTED_OUT) cannot transition to anything else.

### Strategy Pattern (Swappable Integrations)

External APIs are behind interfaces. The service layer calls a `Classifier` or `Sender` — it never imports `openai` or `nylas` directly.

```python
# config.py — swap providers with an env var
email_provider: str = "nylas"      # nylas | mock
llm_provider: str = "openai"       # openai | anthropic | mock
```

This gives us: mock providers for testing (no API calls in CI), and the ability to swap OpenAI for Anthropic or Nylas for SendGrid by changing one line.

### Observer Pattern (via Celery Tasks)

When something happens, the system fans out to independent tasks. Each task does one thing. Adding a new reaction means adding one task — zero changes to existing code.

```
"Inbound email received" triggers:
├── classify_reply          (LLM classification)
├── update_enrollment       (mark as replied, cancel follow-ups)
└── log_state_transition    (audit log)

"Reply classified as referral" triggers:
├── extract_referral        (LLM extracts contact info)
└── auto_enroll_referral    (enroll referred person)
```

Three separate Celery queues (`email`, `ai`, `default`) prevent slow LLM calls from blocking email sends.

### Layered Architecture

Each layer has exactly one job. No layer skips a level.

| Layer | Responsibility | Knows About | Does NOT Know About |
|-------|---------------|-------------|-------------------|
| API | HTTP in/out, validation | Pydantic, Services | SQLAlchemy, Nylas, OpenAI |
| Service | Business rules, orchestration | Repos, Integrations, Celery | FastAPI, HTTP |
| Repository | Data access, all SQL | SQLAlchemy, DB session | Business rules, APIs |
| Integration | External API wrappers | Nylas SDK, OpenAI SDK | Database, business rules |
| Task | Async invocation + retry policy | Services only | Repositories, Integrations, FastAPI, HTTP |

See `docs/architecture/architecture.md` for complete data flows, retry policies, and file structure.

## Setup

### Prerequisites

- Docker & Docker Compose
- Nylas API credentials
- OpenAI API key

### Environment Variables

Create a `.env` file in the project root:

```env
# Nylas
NYLAS_CLIENT_ID=your_client_id
NYLAS_API_KEY=your_api_key
NYLAS_CALLBACK_URL=http://localhost:8000/api/nylas/callback

# OpenAI
OPENAI_API_KEY=your_openai_key

# Database
DATABASE_URL=postgresql://jooba:jooba@db:5432/jooba

# Redis
REDIS_URL=redis://redis:6379/0

# App
SECRET_KEY=your_secret_key
```

### How to Run

```bash
docker compose up
```

Frontend: http://localhost:3000
Backend API: http://localhost:8000
API docs: http://localhost:8000/docs

## Assumptions & Tradeoffs

### Assumptions

1. **Single recruiter user.** No authentication or multi-user support. The app assumes one operator per instance. Multi-tenancy is architecturally supported (add `client_id` FK) but not implemented.

2. **Personal email outreach.** We assume recruiters reach out to candidates' personal email addresses (sourced from LinkedIn, GitHub, Apollo, etc.), not work emails. This is the standard practice in tech recruiting — contacting someone's work email about leaving their job is unprofessional and risks being seen by their employer.

3. **Days as minutes.** Sequence step delays are in minutes for testing speed. In production, the unit is controlled via an environment variable — the frontend is unit-agnostic and just displays the number.

4. **Email provider agnostic.** The UI says "Email Account," not "Gmail." Nylas abstracts Gmail, Outlook, and other providers behind a single API. Swapping providers requires no frontend changes.

5. **LLM provider swappable.** Classification and referral extraction use an interface pattern. OpenAI is the default, but switching to Anthropic or any other provider is a config change, not a code change.

### Tradeoffs

1. **Synchronous CSV parsing.** CSV uploads are parsed and enrolled synchronously in a single API call. For very large CSVs (10,000+ candidates), this should be moved to a Celery task with progress tracking. For the expected scale (50-500 candidates per upload), synchronous is simpler and fast enough.

2. **No A/B testing.** Sequence steps are fixed per sequence. A/B testing subject lines would require a step variant model and random assignment logic. Deferred to keep the data model simple.

3. **No deliverability controls.** No sending limits UI, no custom tracking domain, no SPF/DKIM configuration. The backend has a basic token bucket (40 sends/minute) but this isn't exposed to the user. A production tool would need sender reputation management.

4. **No ATS integration.** Candidates live in Jooba only. There's no push to Greenhouse, Lever, or Ashby. This is the most requested feature for v2.

5. **Opt-out is per-enrollment, not per-candidate.** Unsubscribing marks one enrollment as `OPTED_OUT`, but if the same candidate is in another sequence, they keep receiving those emails. For a single-recruiter running 2-3 sequences, this is unlikely to occur. A production system would add a `do_not_contact` flag on the Candidate record — checked by the scheduler before sending and by the enrollment flow before enrolling. One column, two checks. Not building it now because the single-user scope makes multi-sequence overlap rare.

6. **No cross-sequence deduplication.** A candidate can be enrolled in multiple sequences simultaneously (e.g., "Sr Backend Engineer" and "ML Platform Engineer"). The system does not prevent this or warn the recruiter. In practice this is rare — a recruiter targeting the same person for two different roles would know — but at scale with multiple sequences running, a candidate could receive overlapping outreach. A production system would check active enrollments at enrollment time and surface a warning: "Jane Chen is already in 'Sr Backend Engineer' (Step 2 of 3)."

7. **No authentication (per spec).** The task spec says "assume a single recruiter user, no authentication required." All API endpoints are publicly accessible. This is acceptable for a locally-running Dockerized demo but means the app should never be exposed to an untrusted network without adding auth middleware. A production deployment would add bearer token or session-based authentication.

8. **Referral auto-enrollment trusts LLM output.** When the LLM classifies a reply as a referral, it extracts the referred person's name and email and can auto-enroll them in a sequence. A malicious candidate could craft a reply that manipulates the LLM into extracting a fabricated referral (prompt injection), causing unsolicited emails to an innocent person from the recruiter's real email account. The current mitigation: referrals surface in the UI for recruiter review before enrollment. A production system would add structured output constraints on LLM responses, validate that extracted emails appear literally in the reply text, and require explicit recruiter confirmation before any auto-enrollment.

9. **Inbound email HTML is stored as-is.** Candidate reply HTML is stored in the database and rendered in the recruiter's inbox view. A malicious candidate could include JavaScript in their email body (stored XSS). The frontend must sanitize all inbound HTML before rendering — using DOMPurify or rendering inside a sandboxed iframe. This is a frontend implementation concern, not an architectural one, but worth calling out.

## What I'd Do With 2-3 More Days

1. **ATS integration** — Push interested candidates to Greenhouse/Lever via their APIs. Add a "Move to Pipeline" action in the Inbox that creates an ATS candidate with the full email thread attached.

2. **AI sequence generation** — The architecture already supports this (see `docs/architecture/architecture.md` section 5.2). The recruiter provides role context, the LLM generates email steps. Built-in templates for common patterns (cold outreach, warm referral, re-engagement). The step editor stays the same — generation is just an input method.

3. **Deliverability dashboard** — Sending limits per day, bounce rate tracking, domain warmup progress. Critical for any outreach tool that wants to keep recruiter accounts out of spam.

4. **Outlook/Microsoft 365 testing** — Nylas supports it, but the OAuth flow and webhook behavior differ slightly from Gmail. Needs testing and potentially different callback handling.

5. **Team features** — Multiple recruiters sharing sequences, per-recruiter analytics, role-based access. The layered architecture supports this cleanly — add a `user_id` FK and scope queries.
