/** Matches `app.models.enums.SequenceStatus` JSON values. */
export type SequenceStatus = 'draft' | 'active' | 'paused' | 'archived'

/** Matches `app.models.enums.EnrollmentStatus` JSON values. */
export type EnrollmentStatus = 'active' | 'replied' | 'completed' | 'bounced' | 'opted_out' | 'paused'

/** Matches `app.models.enums.Sentiment` JSON values. */
export type Sentiment = 'interested' | 'not_interested' | 'referral' | 'neutral'

/** Matches `app.models.enums.EmailDirection` JSON values. */
export type EmailDirection = 'inbound' | 'outbound'

export interface SequenceStep {
  id: string
  step_order: number
  subject: string
  body_html: string
  /**
   * Delay before this step relative to the prior send (or enrollment start for step 1). Unit is defined by the
   * product/scheduler only; API and UI expose the numeric value as-is (stored as `delay_minutes` in the DB).
   */
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

export interface PaginatedSequences {
  items: SequenceListItem[]
  total: number
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

export interface NylasConnection {
  connected: boolean
  email: string | null
  provider: string | null
  connected_at: string | null
}

export interface NylasAuthUrlResponse {
  url: string
}

export interface NylasDisconnectResponse {
  status: 'disconnected'
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

export interface InboxReply {
  id: string
  enrollment_id: string
  candidate_name: string
  candidate_email: string
  body_snippet: string
  sentiment: Sentiment | null
  sentiment_reasoning: string | null
  sequence_name: string
  created_at: string
  is_unreplied: boolean
}

export interface ThreadEvent {
  id: string
  direction: EmailDirection
  subject: string | null
  body_html: string | null
  body_text: string | null
  sentiment: Sentiment | null
  sentiment_reasoning: string | null
  is_manual_reply: boolean
  step_index: number | null
  created_at: string
}

export interface ReplyDetail {
  enrollment_id: string
  candidate_name: string
  candidate_email: string
  sequence_name: string
  current_step: number
  total_steps: number
  sentiment: Sentiment | null
  sentiment_reasoning: string | null
  thread: ThreadEvent[]
}

/** Response from POST `/api/replies/{event_id}/reply` (manual send). */
export interface SendReplyResponse {
  message_id: string
  event_id: string
}

export interface SentimentCounts {
  all: number
  interested: number
  not_interested: number
  referral: number
  neutral: number
  unreplied: number
}

/** Matches `app.schemas.analytics.SequenceSummary` (dashboard row per sequence). */
export interface SequenceSummary {
  id: string
  name: string
  status: SequenceStatus
  step_count: number
  enrolled: number
  sent: number
  replied: number
  interested: number
  last_activity: string | null
}

/** Matches `app.schemas.analytics.DashboardStats`. */
export interface DashboardStats {
  total_candidates: number
  total_sent: number
  total_replies: number
  reply_rate: number
  total_interested: number
  unreplied_count: number
  sequences: SequenceSummary[]
}

/** Matches `app.schemas.referral.ReferralInfo` (inbox referral card). */
export interface ReferralInfo {
  name: string | null
  email: string | null
  title: string | null
  company: string | null
  referrer_name: string
  referrer_email: string
  has_email: boolean
  enrolled: boolean
}

/** Transition row in enrollment timeline (`TimelineTransitionEntry`). */
export interface TimelineTransitionEntry {
  type: 'transition'
  timestamp: string
  from_status: EnrollmentStatus | null
  to_status: EnrollmentStatus
  trigger: string
}

/** Email row in enrollment timeline (`TimelineEmailEntry`). */
export interface TimelineEmailEntry {
  type: 'email'
  timestamp: string
  direction: EmailDirection
  subject: string | null
  body_snippet: string
  sentiment: Sentiment | null
  step_index: number | null
  is_manual_reply: boolean
}

/** Discriminated union matching `app.schemas.candidate_timeline.TimelineEntry`. */
export type TimelineEntry = TimelineTransitionEntry | TimelineEmailEntry

/** Matches `app.schemas.candidate_timeline.EnrollmentTimelineResponse` (candidate detail + timeline). */
export interface CandidateDetail {
  candidate: {
    name: string
    email: string
    company?: string | null
    title?: string | null
  }
  enrollment_status: EnrollmentStatus
  timeline: TimelineEntry[]
  referral: { referrer_name: string; referrer_email: string } | null
}
