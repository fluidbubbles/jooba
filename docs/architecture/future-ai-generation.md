# Future: AI Sequence Generation

> This content was extracted from the main architecture document. It describes v2 features not built in v1.
>
> In v1, `about_company`, `selling_points`, and `tone` are intentionally **not** stored as `Sequence` table columns. When AI generation is implemented, these values should be provided as generation request/prompt context, not persisted as standalone sequence metadata columns.

---

## Templates = Saved Generation Presets

A template is NOT a pre-written email. It's a saved set of generation instructions that tell the LLM how to structure the sequence. The LLM generates fresh content every time.

```
SequenceTemplate
├── id
├── name                    ("Cold Outreach - Professional")
├── default_tone            ("professional")
├── default_num_steps       (3)
├── custom_instructions     ("Step 1: personal intro referencing their work.
│                             Step 2: share role details and team culture.
│                             Step 3: soft close, respect their time.")
├── is_system               (true = built-in, false = user-saved)
└── created_at
```

**Built-in templates** ship with the app (3-4 common patterns). **User templates** are created when a recruiter saves a successful generation config for reuse ("Save as Template").

When a recruiter selects a template, it pre-fills the tone, step count, and custom instructions. They still provide role, company, and generation context (`about_company`, `selling_points`, `tone`) at generation time.

## AI Generation Flow

```
Recruiter fills context + selects template + hits "Generate"
        │
        ▼
Frontend → POST /api/sequences/generate
           {
             role_title, company, about_company,
             selling_points, tone, num_steps,
             custom_instructions
           }
        │
        ▼
API Layer: validates input
        │
        ▼
Service Layer: sequence_service.generate_steps(data)
  │
  ├── Build prompt from context + instructions:
  │   "You are a recruiter writing a {num_steps}-step email sequence.
  │    Role: {role_title} at {company}
  │    About: {about_company}
  │    Selling Points: {selling_points}
  │    Tone: {tone}
  │    Instructions: {custom_instructions}
  │
  │    Use {{first_name}}, {{company}}, {{title}} as placeholders.
  │    Return {num_steps} emails with subject lines and HTML bodies."
  │
  ├── llm_client.generate(prompt)  ← synchronous, 2-5 seconds
  │   → returns structured JSON with steps
  │
  └── Parse into StepInput[] and return
        │
        ▼
API Layer: returns StepInput[] to frontend
        │
        ▼
Frontend populates the step editor with generated content
        │
        ▼
Recruiter reviews, edits subject/body/delays as needed
        │
        ▼
(from here, identical to manual flow ↓)
```

**This is synchronous, not Celery.** The user is sitting there waiting. One LLM call, 2-5 seconds. SSE streaming is optional (shows the text generating in real-time in the step editor).

## Save Flow: Generation-Specific Fields

When saving an AI-generated sequence, keep persisted sequence metadata focused on sequence identity/context and pass generation-only inputs as request context:

```
Frontend → POST /api/sequences
           {
             name, steps: StepInput[],
             metadata: { role_title, company, template_id },
             generation_context: { about_company, selling_points,
                                   tone, num_steps, custom_instructions }
           }
```

The `template_id` records which template was used for generation.

`about_company`, `selling_points`, and `tone` remain generation request/prompt inputs and are not persisted as `Sequence` columns in v1.

## "Save as Template"

When a sequence performs well, the recruiter can save its generation config as a reusable template:

```
Recruiter clicks "Save as Template" on a successful sequence
        │
        ▼
Frontend → POST /api/templates
           { name, tone, num_steps, custom_instructions }
        │
        ▼
Saved. Appears in the template picker on the create page.
```

The template stores the generation instructions, NOT the email content. Next time the recruiter uses it for a different role, the LLM generates fresh content with the same structural approach.

## SequenceTemplate Data Model

```
SequenceTemplate
├── id, name, default_tone, default_num_steps
├── custom_instructions
├── is_system (true for built-in)
└── created_at
```
