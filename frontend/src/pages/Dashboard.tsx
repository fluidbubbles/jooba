import { Mail } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import StatCard from '../components/StatCard'

export default function Dashboard() {
  const navigate = useNavigate()

  return (
    <div className="space-y-7 p-8">
      <h1 className="text-[28px] font-semibold tracking-tight text-gray-900">Dashboard</h1>

      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Candidates" value={0} />
        <StatCard label="Sent" value={0} />
        <StatCard label="Replies" value={0} />
        <StatCard label="Interested" value={0} accent />
      </div>

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

      <EmptyState
        icon={Mail}
        title="No sequences yet"
        description="Create your first email sequence to start reaching out to candidates."
        actionLabel="+ Create Sequence"
        onAction={() => navigate('/sequences/new')}
      />
    </div>
  )
}
