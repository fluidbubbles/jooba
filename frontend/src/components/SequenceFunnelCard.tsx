import { Link } from 'react-router-dom'
import StatusBadge from './StatusBadge'
import type { SequenceSummary } from '../lib/types'

function sequenceReplyProgress(summary: SequenceSummary): number {
  const { enrolled, sent, replied } = summary
  if (sent > 0) {
    return Math.min(100, Math.round((replied / sent) * 100))
  }
  if (enrolled > 0) {
    return Math.min(100, Math.round((replied / enrolled) * 100))
  }
  return 0
}

function formatLastActivity(iso: string | null): string {
  if (!iso) {
    return 'No recent activity'
  }
  return `Last activity ${new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })}`
}

type SequenceFunnelCardProps = {
  summary: SequenceSummary
}

export default function SequenceFunnelCard({ summary }: SequenceFunnelCardProps) {
  const progress = sequenceReplyProgress(summary)

  return (
    <Link
      to={`/sequences/${summary.id}`}
      className="block rounded-lg border border-gray-200 bg-white p-5 shadow-sm transition-colors hover:border-gray-300 hover:shadow-md"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold text-gray-900">{summary.name}</h2>
          <p className="mt-0.5 text-[13px] text-gray-500">
            {summary.step_count} {summary.step_count === 1 ? 'step' : 'steps'}
          </p>
        </div>
        <StatusBadge status={summary.status} />
      </div>

      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between text-[11px] font-medium text-gray-500">
          <span>Reply progress</span>
          <span className="text-gray-700">{progress}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
          <div
            className="h-full rounded-full bg-blue-500 transition-[width]"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <dt className="text-[11px] font-medium uppercase tracking-wide text-gray-500">Enrolled</dt>
          <dd className="mt-0.5 text-lg font-semibold text-gray-900">{summary.enrolled}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium uppercase tracking-wide text-gray-500">Sent</dt>
          <dd className="mt-0.5 text-lg font-semibold text-gray-900">{summary.sent}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium uppercase tracking-wide text-gray-500">Replied</dt>
          <dd className="mt-0.5 text-lg font-semibold text-gray-900">{summary.replied}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium uppercase tracking-wide text-gray-500">Interested</dt>
          <dd className="mt-0.5 text-lg font-semibold text-gray-900">{summary.interested}</dd>
        </div>
      </dl>

      <p className="mt-4 border-t border-gray-100 pt-3 text-[13px] text-gray-500">
        {formatLastActivity(summary.last_activity)}
      </p>
    </Link>
  )
}
