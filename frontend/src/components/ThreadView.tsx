import DOMPurify from 'dompurify'
import type { ThreadEvent } from '../lib/types'

interface Props {
  thread: ThreadEvent[]
  candidateName: string
}

export default function ThreadView({ thread, candidateName }: Props) {
  return (
    <div className="space-y-4">
      {thread.map((event) => {
        const sanitizedHtml = DOMPurify.sanitize(event.body_html || event.body_text || '')
        return (
          <div key={event.id} className="bg-[#151827] rounded-lg p-4 border border-gray-700/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-white">
                {event.direction === 'outbound' ? (
                  <>YOU {event.step_index !== null ? `(Step ${event.step_index + 1})` : '(Reply)'}</>
                ) : (
                  candidateName.toUpperCase()
                )}
              </span>
              <span className="text-xs text-gray-500">
                {new Date(event.created_at).toLocaleString('en-US', {
                  month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                })}
              </span>
            </div>
            {event.subject && (
              <p className="text-xs text-gray-500 mb-2">Subject: {event.subject}</p>
            )}
            <div
              className="text-sm text-gray-300 prose prose-invert prose-sm max-w-none"
              dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
            />
          </div>
        )
      })}
    </div>
  )
}
