/** Matches `app.models.enums.SequenceStatus` JSON values. */
export type SequenceStatus = 'draft' | 'active' | 'paused' | 'archived'

/** Matches `app.models.enums.EnrollmentStatus` JSON values. */
export type EnrollmentStatus = 'active' | 'replied' | 'completed' | 'bounced' | 'opted_out' | 'paused'

/** Matches `app.models.enums.Sentiment` JSON values. */
export type Sentiment = 'interested' | 'not_interested' | 'referral' | 'neutral'

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

export interface CandidateInput {
  email: string
  first_name?: string
  last_name?: string
  company?: string
  title?: string
}

export interface EnrollResponse {
  enrolled: number
  skipped: number
  total: number
}

export interface EnrollmentListItem {
  id: string
  candidate_name: string
  candidate_email: string
  current_step: number
  total_steps: number
  status: EnrollmentStatus
  sentiment: Sentiment | null
  created_at: string
}

export interface PaginatedEnrollments {
  items: EnrollmentListItem[]
  total: number
}

export interface SequenceAnalytics {
  enrolled: number
  sent: number
  replied: number
  interested: number
  not_interested: number
  neutral: number
  referral: number
  bounced: number
  opted_out: number
  completed: number
  paused: number
}
