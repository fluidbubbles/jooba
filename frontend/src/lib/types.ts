/** Matches `app.models.enums.SequenceStatus` JSON values. */
export type SequenceStatus = 'draft' | 'active' | 'paused' | 'archived'

export interface SequenceStep {
  id: string
  step_order: number
  subject: string
  body_html: string
  /** Delay in minutes (API field name `delay`). */
  delay: number
}

export interface Sequence {
  id: string
  name: string
  status: SequenceStatus
  role_title: string | null
  company: string | null
  created_at: string
  updated_at: string
  steps: SequenceStep[]
}

export interface SequenceListItem {
  id: string
  name: string
  status: SequenceStatus
  step_count: number
  enrolled_count: number
  replied_count: number
  created_at: string
}

export interface StepInput {
  subject: string
  body_html: string
  delay: number
}

/** Shared optional sequence copy/context fields (nullable in API). */
interface SequenceOptionalMetadata {
  role_title?: string | null
  company?: string | null
}

export interface SequenceCreateInput extends SequenceOptionalMetadata {
  name: string
  steps: StepInput[]
}

export interface SequenceUpdateInput extends SequenceOptionalMetadata {
  name?: string
  steps?: StepInput[]
}

/** Domain error body from API exception handlers (`error` + `code`). */
export interface ApiError {
  error: string
  code: string
}
