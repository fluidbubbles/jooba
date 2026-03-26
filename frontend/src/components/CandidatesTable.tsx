import { useEffect, useState } from 'react'
import { Upload } from 'lucide-react'
import { api } from '../lib/api'
import type { EnrollmentListItem, EnrollmentStatus, Sentiment } from '../lib/types'
import EnrollmentStatusBadge from './EnrollmentStatusBadge'
import EmptyState from './EmptyState'

const SENTIMENT_DOTS: Record<Sentiment, string> = {
  interested: 'bg-green-500',
  not_interested: 'bg-red-500',
  referral: 'bg-purple-500',
  neutral: 'bg-gray-400',
}

const STATUS_OPTIONS: { value: string; label: string }[] = [
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
  onUploadCsv: () => void
  refreshKey: number
}

const PAGE_SIZE = 50

export default function CandidatesTable({ sequenceId, onUploadCsv, refreshKey }: Props) {
  const [enrollments, setEnrollments] = useState<EnrollmentListItem[]>([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)

  useEffect(() => {
    setLoading(true)
    const status = statusFilter === 'all' ? undefined : (statusFilter as EnrollmentStatus)
    api.enrollments
      .list(sequenceId, status, PAGE_SIZE, page * PAGE_SIZE)
      .then((data) => {
        setEnrollments(data.items)
        setTotal(data.total)
        setLoading(false)
      })
      .catch((err) => {
        console.error('Failed to load enrollments:', err)
        setLoading(false)
      })
  }, [sequenceId, statusFilter, page, refreshKey])

  if (loading && enrollments.length === 0) {
    return <div className="text-sm text-gray-500">Loading...</div>
  }

  if (enrollments.length === 0 && statusFilter === 'all') {
    return (
      <EmptyState
        title="No candidates enrolled yet"
        description="Upload a CSV of candidate emails to start sending this sequence."
        actionLabel="Upload CSV"
        onAction={onUploadCsv}
        icon={Upload}
      />
    )
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm text-gray-500">
          {total} candidate{total !== 1 ? 's' : ''}
        </span>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPage(0)
          }}
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
                        aria-hidden
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
            disabled={page === 0}
            className="px-3 py-1 text-sm text-gray-500 transition-colors hover:text-gray-900 disabled:opacity-30"
          >
            Previous
          </button>
          <span className="px-3 py-1 text-sm text-gray-400">
            Page {page + 1} of {Math.ceil(total / PAGE_SIZE)}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={(page + 1) * PAGE_SIZE >= total}
            className="px-3 py-1 text-sm text-gray-500 transition-colors hover:text-gray-900 disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
