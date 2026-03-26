import { useCallback, useEffect, useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { api, ApiRequestError } from '../lib/api'
import type { EnrollmentListItem, EnrollmentStatus, Sentiment } from '../lib/types'
import EnrollmentStatusBadge from './EnrollmentStatusBadge'
import EmptyState from './EmptyState'

const SENTIMENT_DOTS: Record<Sentiment, string> = {
  interested: 'bg-green-500',
  not_interested: 'bg-red-500',
  referral: 'bg-purple-500',
  neutral: 'bg-gray-400',
}

type StatusFilter = 'all' | EnrollmentStatus

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'replied', label: 'Replied' },
  { value: 'completed', label: 'Completed' },
  { value: 'bounced', label: 'Bounced' },
  { value: 'opted_out', label: 'Opted Out' },
  { value: 'paused', label: 'Paused' },
]

interface Props {
  sequenceId: string
  onUploadCsv?: () => void
  refreshKey: number
}

const PAGE_SIZE = 50

export default function CandidatesTable({ sequenceId, onUploadCsv, refreshKey }: Props) {
  const [enrollments, setEnrollments] = useState<EnrollmentListItem[]>([])
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const requestIdRef = useRef(0)

  const loadEnrollments = useCallback(async () => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    const isStaleRequest = () => requestId !== requestIdRef.current

    setLoading(true)
    setError(null)
    const status = statusFilter === 'all' ? undefined : statusFilter
    try {
      const data = await api.enrollments.list(sequenceId, status, PAGE_SIZE, page * PAGE_SIZE)
      if (isStaleRequest()) return

      setTotal(data.total)
      const maxPage = Math.max(0, Math.ceil(data.total / PAGE_SIZE) - 1)
      if (page > maxPage) {
        setPage(maxPage)
        return
      }
      setEnrollments(data.items)
    } catch (err) {
      if (isStaleRequest()) return

      console.error('Failed to load enrollments:', err)
      setError(
        err instanceof ApiRequestError ? err.message : 'Failed to load candidates. Please try again.',
      )
    } finally {
      if (!isStaleRequest()) {
        setLoading(false)
      }
    }
  }, [sequenceId, statusFilter, page])

  useEffect(() => {
    void loadEnrollments()
    // refreshKey is a cache-buster: the parent increments it to trigger a re-fetch
  }, [loadEnrollments, refreshKey])

  if (loading && enrollments.length === 0) {
    return (
      <div role="status" aria-live="polite" className="text-sm text-gray-500">
        Loading...
      </div>
    )
  }

  if (error && enrollments.length === 0) {
    return (
      <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        <p>{error}</p>
        <button
          type="button"
          onClick={() => void loadEnrollments()}
          className="mt-2 text-sm font-medium text-red-700 underline"
        >
          Retry
        </button>
      </div>
    )
  }

  if (enrollments.length === 0 && statusFilter === 'all') {
    return (
      <EmptyState
        title="No candidates enrolled yet"
        description="Upload a CSV of candidate emails to start sending this sequence."
        actionLabel={onUploadCsv ? 'Upload CSV' : undefined}
        onAction={onUploadCsv}
        icon={Upload}
      />
    )
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const hasPreviousPage = page > 0
  const hasNextPage = page + 1 < totalPages

  return (
    <div>
      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm text-gray-500">
          {total} candidate{total !== 1 ? 's' : ''}
        </span>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as StatusFilter)
            setPage(0)
          }}
          aria-label="Filter by status"
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Candidate
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Email
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Step
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Sentiment
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {enrollments.map((e) => (
              <tr key={e.id} className="transition-colors hover:bg-gray-50">
                <td className="px-6 py-4 text-sm font-medium text-gray-900">{e.candidate_name}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{e.candidate_email}</td>
                <td className="px-6 py-4 text-sm text-gray-700">
                  {e.current_step} of {e.total_steps}
                </td>
                <td className="px-6 py-4">
                  <EnrollmentStatusBadge status={e.status} />
                </td>
                <td className="px-6 py-4">
                  {e.sentiment ? (
                    <span className="inline-flex items-center gap-1.5 text-xs text-gray-700">
                      <span
                        className={`h-2 w-2 rounded-full ${SENTIMENT_DOTS[e.sentiment]}`}
                        aria-hidden="true"
                      />
                      {e.sentiment.replace('_', ' ')}
                    </span>
                  ) : (
                    <span className="text-gray-400">{'\u2014'}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {total > PAGE_SIZE && (
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={!hasPreviousPage}
            className="px-3 py-1 text-sm text-gray-500 transition-colors hover:text-gray-900 disabled:opacity-30"
          >
            Previous
          </button>
          <span className="px-3 py-1 text-sm text-gray-400">
            Page {page + 1} of {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasNextPage}
            className="px-3 py-1 text-sm text-gray-500 transition-colors hover:text-gray-900 disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
