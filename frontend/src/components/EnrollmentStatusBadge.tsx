import type { EnrollmentStatus } from '../lib/types'

const ENROLLMENT_STYLES: Record<EnrollmentStatus, { dot: string; bg: string; text: string; label: string }> = {
  active: { dot: 'bg-blue-500', bg: 'bg-blue-50', text: 'text-blue-700', label: 'Active' },
  replied: { dot: 'bg-yellow-500', bg: 'bg-yellow-50', text: 'text-yellow-700', label: 'Replied' },
  completed: { dot: 'bg-gray-400', bg: 'bg-gray-100', text: 'text-gray-600', label: 'Completed' },
  bounced: { dot: 'bg-red-500', bg: 'bg-red-50', text: 'text-red-700', label: 'Bounced' },
  opted_out: { dot: 'bg-gray-500', bg: 'bg-gray-100', text: 'text-gray-600', label: 'Opted Out' },
  paused: { dot: 'bg-amber-500', bg: 'bg-amber-50', text: 'text-amber-700', label: 'Paused' },
}

export default function EnrollmentStatusBadge({ status }: { status: EnrollmentStatus }) {
  const style = ENROLLMENT_STYLES[status]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${style.bg} ${style.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} aria-hidden />
      {style.label}
    </span>
  )
}
