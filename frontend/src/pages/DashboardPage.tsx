import { Mail } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import SequenceFunnelCard from '../components/SequenceFunnelCard'
import StatCard from '../components/StatCard'
import { api, ApiRequestError } from '../lib/api'
import type { DashboardStats } from '../lib/types'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const loadTokenRef = useRef(0)

  const loadDashboard = useCallback(async () => {
    const token = ++loadTokenRef.current
    setLoading(true)
    setError(null)
    try {
      const data = await api.analytics.dashboard()
      if (loadTokenRef.current !== token) {
        return
      }
      setStats(data)
    } catch (err) {
      console.error('Failed to load dashboard', err)
      if (loadTokenRef.current !== token) {
        return
      }
      setError(err instanceof ApiRequestError ? err.message : 'Failed to load dashboard')
    } finally {
      if (loadTokenRef.current === token) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    void loadDashboard()
  }, [loadDashboard])

  const handleRetry = () => {
    void loadDashboard()
  }

  const hasUnreplied = (stats?.unreplied_count ?? 0) > 0

  return (
    <div className="space-y-7 p-8">
      <h1 className="text-[28px] font-semibold tracking-tight text-gray-900">Dashboard</h1>

      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3"
        >
          <span className="text-[13px] text-red-800">{error}</span>
          <button
            type="button"
            onClick={handleRetry}
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
          Loading dashboard…
        </div>
      )}

      {!loading && !error && stats && (
        <>
          <div className="grid grid-cols-4 gap-4">
            <StatCard label="Candidates" value={stats.total_candidates} />
            <StatCard label="Sent" value={stats.total_sent} />
            <StatCard
              label="Replies"
              value={stats.total_replies}
              percentage={stats.total_sent > 0 ? `${stats.reply_rate}%` : undefined}
            />
            {hasUnreplied ? (
              <Link
                to="/inbox?filter=interested"
                className="block rounded-lg outline-none ring-offset-2 focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <StatCard
                  label="Interested"
                  value={stats.total_interested}
                  percentage={`${stats.unreplied_count} unreplied`}
                  accent
                />
              </Link>
            ) : (
              <StatCard label="Interested" value={stats.total_interested} accent />
            )}
          </div>

          {stats.sequences.length === 0 ? (
            <EmptyState
              icon={Mail}
              title="No sequences yet"
              description="Create your first email sequence to start reaching out to candidates."
              actionLabel="+ Create Sequence"
              onAction={() => navigate('/sequences/new')}
            />
          ) : (
            <section aria-label="Sequence funnels" className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900">Sequences</h2>
              <div className="grid gap-4 md:grid-cols-2">
                {stats.sequences.map((s) => (
                  <SequenceFunnelCard key={s.id} summary={s} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
