import { Mail, Plus } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import StatusBadge from '../components/StatusBadge'
import { api, ApiRequestError } from '../lib/api'
import type { SequenceListItem } from '../lib/types'

const TABLE_HEADERS = ['Name', 'Status', 'Steps', 'Enrolled', 'Replied', 'Created'] as const

function formatCreatedAt(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export default function SequencesList() {
  const navigate = useNavigate()
  const [items, setItems] = useState<SequenceListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadSequences = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.sequences.list()
      setItems(data)
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : 'Failed to load sequences')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSequences()
  }, [loadSequences])

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] font-semibold tracking-tight text-gray-900">Sequences</h1>
        <button
          type="button"
          onClick={() => navigate('/sequences/new')}
          className="flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
        >
          <Plus size={14} />
          Create Sequence
        </button>
      </div>

      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3"
        >
          <span className="text-[13px] text-red-800">{error}</span>
          <button
            type="button"
            onClick={() => void loadSequences()}
            className="shrink-0 rounded-md bg-white px-3 py-1.5 text-[13px] font-medium text-red-800 ring-1 ring-red-200 transition-colors hover:bg-red-50"
          >
            Retry
          </button>
        </div>
      )}

      {loading && (
        <div
          role="status"
          aria-live="polite"
          className="rounded-xl border border-gray-200 bg-white p-10 text-center text-sm text-gray-500 shadow-sm"
        >
          Loading sequences…
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <EmptyState
          icon={Mail}
          title="No sequences yet"
          description="Create your first sequence to start automated outreach."
          actionLabel="+ Create Sequence"
          onAction={() => navigate('/sequences/new')}
        />
      )}

      {!loading && !error && items.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 text-left text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {TABLE_HEADERS.map((label) => (
                    <th
                      key={label}
                      scope="col"
                      className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500"
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {items.map((row) => (
                  <tr key={row.id} className="transition-colors hover:bg-gray-50">
                    <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-900">
                      <Link
                        to={`/sequences/${row.id}`}
                        className="rounded-sm text-blue-600 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70"
                      >
                        {row.name}
                      </Link>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">{row.step_count}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                      {row.enrolled_count}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                      {row.replied_count}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                      {formatCreatedAt(row.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
