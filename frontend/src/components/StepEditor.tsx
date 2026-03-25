import { Trash2 } from 'lucide-react'
import type { ChangeEvent } from 'react'
import type { StepInput } from '../lib/types'

export interface StepEditorProps {
  index: number
  step: StepInput
  totalSteps: number
  disabled?: boolean
  onChange: (patch: Partial<StepInput>) => void
  onRemove: () => void
}

export default function StepEditor({
  index,
  step,
  totalSteps,
  disabled = false,
  onChange,
  onRemove,
}: StepEditorProps) {
  const isFirst = index === 0
  const stepNumber = index + 1
  const showConnector = index < totalSteps - 1

  function handleDelayChange(e: ChangeEvent<HTMLInputElement>) {
    const raw = e.target.valueAsNumber
    const next = Number.isFinite(raw) ? Math.max(1, Math.floor(raw)) : 1
    onChange({ delay: next })
  }

  return (
    <div className="flex gap-4">
      <div className="flex w-10 shrink-0 flex-col items-center pt-1">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold text-white"
          aria-hidden
        >
          {stepNumber}
        </div>
        {showConnector ? (
          <div className="mt-2 w-px flex-1 min-h-6 bg-gray-200" aria-hidden />
        ) : null}
      </div>

      <div className="min-w-0 flex-1 space-y-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-sm font-semibold text-gray-900">Step {stepNumber}</h3>
          {totalSteps > 1 ? (
            <button
              type="button"
              onClick={onRemove}
              disabled={disabled}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-red-700 transition-colors hover:bg-red-50"
            >
              <Trash2 size={14} aria-hidden />
              Remove
            </button>
          ) : null}
        </div>

        <div className="space-y-2">
          <label htmlFor={`step-${index}-subject`} className="block text-xs font-medium text-gray-600">
            Subject
          </label>
          <input
            id={`step-${index}-subject`}
            type="text"
            value={step.subject}
            onChange={(e) => onChange({ subject: e.target.value })}
            disabled={disabled}
            className="h-10 w-full rounded-md border border-gray-200 px-3 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            autoComplete="off"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor={`step-${index}-body`} className="block text-xs font-medium text-gray-600">
            Body
          </label>
          <textarea
            id={`step-${index}-body`}
            value={step.body_html}
            onChange={(e) => onChange({ body_html: e.target.value })}
            rows={6}
            disabled={disabled}
            className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {isFirst ? (
          <p className="text-sm text-gray-600">
            <span className="font-medium text-gray-800">Sends immediately</span>
            <span className="text-gray-500"> — the first step has no delay.</span>
          </p>
        ) : (
          <div className="space-y-2">
            <label htmlFor={`step-${index}-delay`} className="block text-xs font-medium text-gray-600">
              Delay before send (minutes)
            </label>
            <input
              id={`step-${index}-delay`}
              type="number"
              min={1}
              value={step.delay}
              onChange={handleDelayChange}
              disabled={disabled}
              className="h-10 w-32 rounded-md border border-gray-200 px-3 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        )}
      </div>
    </div>
  )
}
