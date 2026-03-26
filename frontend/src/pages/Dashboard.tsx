import { useEffect, useState } from 'react'
import { Mail } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import StatCard from '../components/StatCard'
import StatusBadge from '../components/StatusBadge'
import { useNylasConnection } from '../lib/nylasConnectionContext'
import { api } from '../lib/api'
import type { Sequence } from '../lib/types'

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { connection, loading: nylasLoading } = useNylasConnection()
  const isConnected = connection?.connected === true
  const [sequences, setSequences] = useState<Sequence[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.sequences.list().then((data) => {
      setSequences(data)
      setLoading(false)
    }).catch((err) => {
      console.error('Failed to load sequences', err)
      setLoading(false)
    })
  }, [])

  const totalCandidates = sequences.reduce((sum, s) => sum + (s.enrolled_count ?? 0), 0)
  const totalReplied = sequences.reduce((sum, s) => sum + (s.replied_count ?? 0), 0)

  return (
    <div className="space-y-7 p-8">
      <h1 className="text-[28px] font-semibold tracking-tight text-gray-900">Dashboard</h1>

      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Candidates" value={totalCandidates} />
        <StatCard label="Sequences" value={sequences.length} />
        <StatCard label="Replies" value={totalReplied} />
        <StatCard label="Interested" value={0} accent />
      </div>

      {!nylasLoading && !isConnected && (
        <div className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <span className="text-[13px] text-amber-800">
            ⚠ Email not connected — connect your inbox in Settings to start sending.
          </span>
          <button
            type="button"
            onClick={() => navigate('/settings')}
            className="text-[13px] font-medium text-blue-500 hover:text-blue-600"
          >
            Go to Settings →
          </button>
        </div>
      )}

      {!loading && sequences.length === 0 && (
        <EmptyState
          icon={Mail}
          title="No sequences yet"
          description="Create your first email sequence to start reaching out to candidates."
          actionLabel="+ Create Sequence"
          onAction={() => navigate('/sequences/new')}
        />
      )}

      {sequences.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Active Sequences</h2>
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Sequence</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Steps</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Enrolled</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Replied</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {sequences.map((seq) => (
                  <tr
                    key={seq.id}
                    onClick={() => navigate(`/sequences/${seq.id}`)}
                    className="cursor-pointer hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <p className="text-sm font-medium text-gray-900">{seq.name}</p>
                    </td>
                    <td className="px-4 py-4">
                      <StatusBadge status={seq.status} />
                    </td>
                    <td className="px-4 py-4 text-center text-sm text-gray-600">{seq.step_count}</td>
                    <td className="px-4 py-4 text-center text-sm text-gray-600">{seq.enrolled_count}</td>
                    <td className="px-4 py-4 text-center text-sm text-gray-600">
                      {seq.replied_count}
                      {seq.enrolled_count > 0 && (
                        <span className="text-gray-400 text-xs ml-1">
                          ({Math.round((seq.replied_count / seq.enrolled_count) * 100)}%)
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-4 text-right text-sm text-gray-400">{timeAgo(seq.created_at)}</td>
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
