import type {
  ApiError,
  CandidateDetail,
  CandidateInput,
  DashboardStats,
  EnrollmentStatus,
  EnrollResponse,
  InboxReply,
  NylasAuthUrlResponse,
  NylasConnection,
  NylasDisconnectResponse,
  PaginatedEnrollments,
  ReferralInfo,
  ReplyDetail,
  SendReplyResponse,
  Sequence,
  SequenceAnalytics,
  SequenceCreateInput,
  PaginatedSequences,
  SequenceStatus,
  SequenceUpdateInput,
  Sentiment,
  SentimentCounts,
} from './types'

const BASE_URL = '/api'

export class ApiRequestError extends Error {
  readonly status: number
  readonly code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.code = code
  }
}

export function getApiErrorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiRequestError ? err.message : fallback
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers)
  const hasBody = options?.body !== undefined && options.body !== null
  if (hasBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText })) as Partial<ApiError>
    throw new ApiRequestError(res.status, body.error || res.statusText, body.code)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  sequences: {
    list(params?: { q?: string; status?: SequenceStatus; sort?: string; limit?: number; offset?: number }): Promise<PaginatedSequences> {
      const qs = new URLSearchParams()
      if (params?.q) qs.set('q', params.q)
      if (params?.status) qs.set('status', params.status)
      if (params?.sort) qs.set('sort', params.sort)
      if (params?.limit != null) qs.set('limit', String(params.limit))
      if (params?.offset != null) qs.set('offset', String(params.offset))
      const suffix = qs.toString() ? `?${qs}` : ''
      return apiFetch<PaginatedSequences>(`/sequences${suffix}`)
    },

    get(sequenceId: string): Promise<Sequence> {
      return apiFetch<Sequence>(`/sequences/${sequenceId}`)
    },

    create(body: SequenceCreateInput): Promise<Sequence> {
      return apiFetch<Sequence>('/sequences', { method: 'POST', body: JSON.stringify(body) })
    },

    update(sequenceId: string, body: SequenceUpdateInput): Promise<Sequence> {
      return apiFetch<Sequence>(`/sequences/${sequenceId}`, { method: 'PUT', body: JSON.stringify(body) })
    },

    delete(sequenceId: string): Promise<void> {
      return apiFetch<void>(`/sequences/${sequenceId}`, { method: 'DELETE' })
    },

    changeStatus(sequenceId: string, status: SequenceStatus): Promise<Sequence> {
      return apiFetch<Sequence>(`/sequences/${sequenceId}/status`, {
        method: 'PUT',
        body: JSON.stringify({ status }),
      })
    },
  },

  enrollments: {
    enroll(sequenceId: string, candidates: CandidateInput[]): Promise<EnrollResponse> {
      return apiFetch<EnrollResponse>(`/sequences/${sequenceId}/enroll`, {
        method: 'POST',
        body: JSON.stringify({ candidates }),
      })
    },

    list(sequenceId: string, status?: EnrollmentStatus, limit = 50, offset = 0): Promise<PaginatedEnrollments> {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
      if (status) params.set('status', status)
      return apiFetch<PaginatedEnrollments>(`/sequences/${sequenceId}/enrollments?${params}`)
    },

    analytics(sequenceId: string): Promise<SequenceAnalytics> {
      return apiFetch<SequenceAnalytics>(`/sequences/${sequenceId}/analytics`)
    },
  },

  analytics: {
    dashboard(): Promise<DashboardStats> {
      return apiFetch<DashboardStats>('/analytics/dashboard')
    },
  },

  referrals: {
    info(eventId: string): Promise<ReferralInfo | null> {
      return apiFetch<ReferralInfo | null>(`/inbox/replies/${eventId}/referral`)
    },

    retry(eventId: string): Promise<ReferralInfo | null> {
      return apiFetch<ReferralInfo | null>(`/inbox/replies/${eventId}/referral/retry`, {
        method: 'POST',
      })
    },

    enroll(eventId: string, sequenceId: string): Promise<EnrollResponse> {
      return apiFetch<EnrollResponse>(`/inbox/replies/${eventId}/referral/enroll`, {
        method: 'POST',
        body: JSON.stringify({ sequence_id: sequenceId }),
      })
    },
  },

  candidates: {
    timeline(enrollmentId: string): Promise<CandidateDetail> {
      return apiFetch<CandidateDetail>(`/enrollments/${enrollmentId}/timeline`)
    },
  },

  nylas: {
    status(): Promise<NylasConnection> {
      return apiFetch<NylasConnection>('/nylas/status')
    },

    authUrl(): Promise<NylasAuthUrlResponse> {
      return apiFetch<NylasAuthUrlResponse>('/nylas/auth-url')
    },

    disconnect(): Promise<NylasDisconnectResponse> {
      return apiFetch<NylasDisconnectResponse>('/nylas/disconnect', { method: 'DELETE' })
    },
  },

  inbox: {
    replies(sentiment?: Sentiment | 'all' | 'unreplied', limit = 50, offset = 0): Promise<InboxReply[]> {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
      if (sentiment && sentiment !== 'all') params.set('sentiment', sentiment)
      return apiFetch<InboxReply[]>(`/inbox/replies?${params}`)
    },

    counts(): Promise<SentimentCounts> {
      return apiFetch<SentimentCounts>('/inbox/counts')
    },

    detail(eventId: string): Promise<ReplyDetail> {
      return apiFetch<ReplyDetail>(`/inbox/replies/${eventId}`)
    },

    sendReply(eventId: string, bodyHtml: string): Promise<SendReplyResponse> {
      return apiFetch<SendReplyResponse>(`/replies/${eventId}/reply`, {
        method: 'POST',
        body: JSON.stringify({ body_html: bodyHtml }),
      })
    },
  },
}
