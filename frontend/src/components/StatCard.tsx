interface StatCardProps {
  label: string
  value: number | string
  percentage?: string
  accent?: boolean
}

export default function StatCard({ label, value, percentage, accent }: StatCardProps) {
  return (
    <div
      className={`rounded-lg border p-5 ${
        accent
          ? 'border-green-200 bg-green-50 shadow-sm shadow-green-500/10'
          : 'border-gray-200 bg-white shadow-sm'
      }`}
    >
      <p className={`text-[13px] font-medium ${accent ? 'text-green-600' : 'text-gray-500'}`}>
        {label}
      </p>
      <div className="flex items-end gap-2">
        <span
          className={`text-[32px] font-semibold tracking-tight ${
            accent ? 'text-green-600' : 'text-gray-900'
          }`}
        >
          {value}
        </span>
        {percentage && (
          <span
            className={`mb-1 text-sm font-medium ${accent ? 'text-green-600' : 'text-gray-500'}`}
          >
            {percentage}
          </span>
        )}
      </div>
    </div>
  )
}
