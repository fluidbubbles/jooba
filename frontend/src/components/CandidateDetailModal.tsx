import { X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiRequestError } from '../lib/api'
import type { CandidateDetail, TimelineEntry } from '../lib/types'
import EnrollmentStatusBadge from './EnrollmentStatusBadge'
import SentimentBadge from './SentimentBadge'

type CandidateDetailModalProps = {
  enrollmentId: string
  onClose: () => void
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function transitionLabel(entry: Extract<TimelineEntry, { type: 'transition' }>): string {
  switch (entry.trigger) {
    case 'enrolled':
      return 'Enrolled in sequence'
    case 'email_sent':
      return 'Email sent'
    case 'reply_received':
      return 'Reply received'
    case 'completed':
      return 'Sequence completed'
    case 'unsubscribe_clicked':
      return 'Unsubscribed'
    case 'max_retries_exhausted':
      return 'Paused (send failures)'
    case 'manual_reply_sent':
      return 'Recruiter replied'
    default:
      return entry.trigger || 'Status changed'
  }
}

function TimelineItem({ entry }: { entry: TimelineEntry }) {
  if (entry.type === 'transition') {
    return (
      <div className="flex items-start gap-3">
        <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-gray-400" aria-hidden="true" />
        <div>
          <p className="text-sm text-gray-800">{transitionLabel(entry)}</p>
          <p className="text-xs text-gray-500">{formatTimestamp(entry.timestamp)}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-3">
      <span
        className={`mt-2 h-2 w-2 shrink-0 rounded-full ${
          entry.direction === 'outbound' ? 'bg-blue-500' : 'bg-amber-500'
        }`}
        aria-hidden="true"
      />
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm text-gray-800">
            {entry.direction === 'outbound'
              ? `${entry.is_manual_reply ? 'Recruiter replied' : `Step ${(entry.step_index ?? 0) + 1} sent`}`
              : 'Candidate replied'}
            {entry.subject ? ` - "${entry.subject}"` : ''}
          </p>
          {entry.sentiment && <SentimentBadge sentiment={entry.sentiment} />}
        </div>
        {entry.body_snippet && (
          <p className="mt-0.5 text-xs text-gray-600">&quot;{entry.body_snippet}&quot;</p>
        )}
        <p className="mt-0.5 text-xs text-gray-500">{formatTimestamp(entry.timestamp)}</p>
      </div>
    </div>
  )
}

export default function CandidateDetailModal({ enrollmentId, onClose }: CandidateDetailModalProps) {
  const [data, setData] = useState<CandidateDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const loadTokenRef = useRef(0)
  const modalRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  const loadTimeline = useCallback(async () => {
    const token = ++loadTokenRef.current
    setLoading(true)
    setError(null)
    try {
      const timelineData = await api.candidates.timeline(enrollmentId)
      if (loadTokenRef.current !== token) {
        return
      }
      setData(timelineData)
    } catch (err) {
      console.error('Failed to load candidate timeline', err)
      if (loadTokenRef.current !== token) {
        return
      }
      setData(null)
      setError(err instanceof ApiRequestError ? err.message : 'Failed to load candidate timeline.')
    } finally {
      if (loadTokenRef.current === token) {
        setLoading(false)
      }
    }
  }, [enrollmentId])

  useEffect(() => {
    void loadTimeline()
  }, [loadTimeline])

  useEffect(() => {
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeButtonRef.current?.focus()

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (event.key !== 'Tab' || !modalRef.current) return

      const focusable = Array.from(
        modalRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]',
        ),
      ).filter((element) => {
        if (element.getAttribute('tabindex') === '-1') return false
        if (element.hasAttribute('disabled')) return false
        if (element.getAttribute('aria-hidden') === 'true') return false
        return element.getClientRects().length > 0
      })
      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (event.shiftKey && active === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      previousFocusRef.current?.focus()
    }
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="Candidate activity timeline"
        className="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {data ? data.candidate.name : 'Candidate detail'}
            </h2>
            {data && (
              <p className="text-sm text-gray-500">
                {data.candidate.email}
                {data.candidate.title && ` - ${data.candidate.title}`}
                {data.candidate.company && ` at ${data.candidate.company}`}
              </p>
            )}
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close candidate detail"
            className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
          >
            <X size={20} aria-hidden />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div role="status" aria-live="polite" className="text-sm text-gray-500">
              Loading timeline...
            </div>
          ) : error ? (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <p>{error}</p>
              <button
                type="button"
                onClick={() => void loadTimeline()}
                className="mt-2 text-sm font-medium text-red-700 underline"
              >
                Retry
              </button>
            </div>
          ) : data ? (
            <div>
              <div className="mb-4">
                <EnrollmentStatusBadge status={data.enrollment_status} />
              </div>

              {data.referral && (
                <div className="mb-4 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-sm text-violet-800">
                  Referred by: {data.referral.referrer_name} ({data.referral.referrer_email})
                </div>
              )}

              <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-gray-500">
                Activity Timeline
              </h3>
              {data.timeline.length === 0 ? (
                <p className="text-sm text-gray-500">No activity yet.</p>
              ) : (
                <div className="ml-1 space-y-4 border-l border-gray-200 pl-4">
                  {data.timeline.map((entry, index) => (
                    <TimelineItem key={`${entry.type}-${entry.timestamp}-${index}`} entry={entry} />
                  ))}
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
