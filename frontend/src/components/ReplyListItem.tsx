import { Clock } from 'lucide-react'
import type { InboxReply } from '../lib/types'

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

interface Props {
  reply: InboxReply
  isSelected: boolean
  onClick: () => void
}

export default function ReplyListItem({ reply, isSelected, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className={`px-4 py-3 cursor-pointer border-b border-gray-100 transition-colors ${
        isSelected
          ? 'bg-amber-50'
          : 'bg-white hover:bg-gray-50'
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-0.5">
        <span className="text-sm font-semibold text-gray-900 truncate">{reply.candidate_name}</span>
        <span className="text-xs text-gray-400 shrink-0">{timeAgo(reply.created_at)}</span>
      </div>
      {reply.is_unreplied && (
        <span className="inline-flex items-center gap-1 text-xs text-amber-600 font-medium mb-0.5">
          <Clock size={11} />
          Unreplied
        </span>
      )}
      <p className="text-xs text-gray-500 mb-0.5 truncate">{reply.sequence_name}</p>
      <p className="text-sm text-gray-500 line-clamp-2">{reply.body_snippet}</p>
    </div>
  )
}
