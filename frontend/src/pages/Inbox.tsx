import { Inbox as InboxIcon } from 'lucide-react'
import EmptyState from '../components/EmptyState'

const filterTabs = [
  'All (0)',
  'Interested (0)',
  'Not Interested (0)',
  'Referral (0)',
  'Neutral (0)',
]

export default function Inbox() {
  return (
    <div className="space-y-6 p-8">
      <h1 className="text-[28px] font-semibold tracking-tight text-gray-900">Inbox</h1>

      <div className="flex gap-1">
        {filterTabs.map((tab, i) => (
          <button
            key={tab}
            type="button"
            className={`rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors ${
              i === 0
                ? 'bg-blue-500 text-white'
                : 'border border-gray-200 text-gray-500 hover:border-gray-300'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      <EmptyState
        icon={InboxIcon}
        title="No replies yet"
        description="Replies from candidates will appear here once your sequences start sending and people respond."
      />
    </div>
  )
}
