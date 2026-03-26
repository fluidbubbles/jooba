import { Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import SequencesTable from '../components/SequencesTable'

export default function SequencesList() {
  const navigate = useNavigate()

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
      <SequencesTable />
    </div>
  )
}
