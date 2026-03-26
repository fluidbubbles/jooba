import type { SequenceStatus } from '../lib/types'

const STATUS_CONFIG: Record<SequenceStatus, { label: string; className: string }> = {
  draft: { label: 'Draft', className: 'bg-gray-100 text-gray-700 ring-gray-200' },
  active: { label: 'Active', className: 'bg-emerald-50 text-emerald-800 ring-emerald-200' },
  paused: { label: 'Paused', className: 'bg-amber-50 text-amber-900 ring-amber-200' },
  archived: { label: 'Archived', className: 'bg-slate-100 text-slate-600 ring-slate-200' },
}

type StatusBadgeProps = {
  status: SequenceStatus
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const { label, className } = STATUS_CONFIG[status]
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${className}`}
    >
      {label}
    </span>
  )
}
