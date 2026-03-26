import { Clock } from 'lucide-react'
import type { InboxReply } from '../lib/types'
import SentimentBadge from './SentimentBadge'

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
      className={`p-4 cursor-pointer border-l-2 transition-colors ${
        isSelected
          ? 'bg-blue-500/10 border-blue-500'
          : 'border-transparent hover:bg-white/5'
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <SentimentBadge sentiment={reply.sentiment} />
        <span className="text-white text-sm font-medium truncate">{reply.candidate_name}</span>
      </div>
      <p className="text-gray-500 text-xs mb-1 truncate">{reply.candidate_email}</p>
      <p className="text-gray-400 text-sm line-clamp-2 mb-2">"{reply.body_snippet}"</p>
      <div className="flex items-center gap-3 text-xs text-gray-500">
        <span>{reply.sequence_name}</span>
        <span>&middot;</span>
        <span>{timeAgo(reply.created_at)}</span>
        {reply.is_unreplied && (
          <>
            <span>&middot;</span>
            <span className="flex items-center gap-1 text-amber-400">
              <Clock size={12} />
              Unreplied
            </span>
          </>
        )}
      </div>
    </div>
  )
}
