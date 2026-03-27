import DOMPurify from 'dompurify'
import type { ThreadEvent } from '../lib/types'

/** Strip quoted email content (blockquotes + "On ... wrote:" lines) from sanitized HTML. */
function stripQuotedContent(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  // Remove all blockquote elements (quoted replies)
  doc.querySelectorAll('blockquote').forEach((el) => el.remove())
  // Remove Gmail-style "gmail_quote" divs
  doc.querySelectorAll('.gmail_quote').forEach((el) => el.remove())
  // Remove "On ... wrote:" attribution lines
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT)
  const toRemove: Node[] = []
  while (walker.nextNode()) {
    const text = walker.currentNode.textContent ?? ''
    if (/^On .+ wrote:\s*$/.test(text.trim())) {
      toRemove.push(walker.currentNode.parentElement ?? walker.currentNode)
    }
  }
  toRemove.forEach((n) => n.parentNode?.removeChild(n))
  return doc.body.innerHTML.trim()
}

interface Props {
  thread: ThreadEvent[]
  candidateName: string
}

export default function ThreadView({ thread, candidateName }: Props) {
  return (
    <div className="space-y-3">
      {thread.map((event) => {
        const sanitizedHtml = stripQuotedContent(
          DOMPurify.sanitize(event.body_html || event.body_text || ''),
        )
        const isInbound = event.direction === 'inbound'
        const dateStr = new Date(event.created_at).toLocaleString('en-US', {
          month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
        })

        if (isInbound) {
          return (
            <div key={event.id} className="rounded-lg border border-green-200 bg-green-50 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-green-700 uppercase">
                  {candidateName}
                </span>
                <span className="text-xs text-gray-500">{dateStr}</span>
              </div>
              {event.subject && (
                <p className="text-xs text-gray-500 mb-2">Subject: {event.subject}</p>
              )}
              <div
                className="text-sm text-gray-700 prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
              />
            </div>
          )
        }

        return (
          <div key={event.id} className="py-2">
            <div className="flex items-center gap-1.5 mb-2">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                YOU {event.step_index !== null ? `(Step ${event.step_index + 1})` : '(Reply)'}
              </span>
              <span className="text-xs text-gray-400">&middot;</span>
              <span className="text-xs text-gray-400">{dateStr}</span>
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
