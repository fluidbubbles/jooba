import DOMPurify from 'dompurify'
import type { ThreadEvent } from '../lib/types'

interface Props {
  thread: ThreadEvent[]
  candidateName: string
}

export default function ThreadView({ thread, candidateName }: Props) {
  return (
    <div className="space-y-3">
      {thread.map((event) => {
        // Sanitize inbound HTML to prevent stored XSS from candidate emails
        const sanitizedHtml = DOMPurify.sanitize(event.body_html || event.body_text || '')
        const isOutbound = event.direction === 'outbound'
        return (
          <div
            key={event.id}
            className={`rounded-lg p-4 border ${
              isOutbound
                ? 'bg-blue-50 border-blue-100'
                : 'bg-gray-50 border-gray-100'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className={`text-sm font-medium ${isOutbound ? 'text-blue-700' : 'text-gray-900'}`}>
                {isOutbound ? (
                  <>You {event.step_index !== null ? `(Step ${event.step_index + 1})` : '(Reply)'}</>
                ) : (
                  candidateName
                )}
              </span>
              <span className="text-xs text-gray-400">
                {new Date(event.created_at).toLocaleString('en-US', {
                  month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                })}
              </span>
            </div>
            {event.subject && (
              <p className="text-xs text-gray-400 mb-2">Subject: {event.subject}</p>
            )}
            <div
              className="text-sm text-gray-700 prose prose-sm max-w-none"
              dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
            />
          </div>
        )
      })}
    </div>
  )
}
