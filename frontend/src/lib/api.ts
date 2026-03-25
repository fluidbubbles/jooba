import type {
  ApiError,
  Sequence,
  SequenceCreateInput,
  SequenceListItem,
  SequenceStatus,
  SequenceUpdateInput,
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

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers)
  if (!headers.has('Content-Type')) {
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

  return res.json() as Promise<T>
}

export const api = {
  sequences: {
    list(): Promise<SequenceListItem[]> {
      return apiFetch<SequenceListItem[]>('/sequences')
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

    changeStatus(sequenceId: string, status: SequenceStatus): Promise<Sequence> {
      return apiFetch<Sequence>(`/sequences/${sequenceId}/status`, {
        method: 'PUT',
        body: JSON.stringify({ status }),
      })
    },
  },
}
