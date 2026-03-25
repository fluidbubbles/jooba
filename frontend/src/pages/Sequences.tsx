import { Mail, Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import EmptyState from '../components/EmptyState'

export default function Sequences() {
  const navigate = useNavigate()

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] font-semibold tracking-tight text-gray-900">Sequences</h1>
        <button
          type="button"
          onClick={() => navigate('/sequences/new')}
          className="flex items-center gap-1.5 rounded-md bg-blue-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-600"
        >
          <Plus size={14} />
          Create Sequence
        </button>
      </div>

      <EmptyState
        icon={Mail}
        title="No sequences yet"
        description="Create your first sequence to start automated outreach."
        actionLabel="+ Create Sequence"
        onAction={() => navigate('/sequences/new')}
      />
    </div>
  )
}
