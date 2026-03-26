import { useEffect, useState } from 'react'
import { Mail } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import StatCard from '../components/StatCard'
import { useNylasConnection } from '../lib/nylasConnectionContext'
import { api } from '../lib/api'
import type { Sequence } from '../lib/types'

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
        <StatCard label="Sequences" value={sequences.length} />
        <StatCard label="Candidates" value={totalCandidates} />
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
    </div>
  )
}
