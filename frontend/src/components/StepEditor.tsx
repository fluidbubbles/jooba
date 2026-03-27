import { ChevronDown, ChevronUp, Trash2 } from 'lucide-react'
import type { ChangeEvent } from 'react'
import type { StepInput } from '../lib/types'

export interface StepEditorProps {
  index: number
  step: StepInput
  totalSteps: number
  disabled?: boolean
  onChange: (patch: Partial<StepInput>) => void
  onRemove: () => void
  onMoveUp?: () => void
  onMoveDown?: () => void
}

export default function StepEditor({
  index,
  step,
  totalSteps,
  disabled = false,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
}: StepEditorProps) {
  const isFirst = index === 0
  const stepNumber = index + 1

  function handleDelayChange(e: ChangeEvent<HTMLInputElement>) {
    const raw = e.target.valueAsNumber
    const next = Number.isFinite(raw) ? Math.max(1, Math.floor(raw)) : 1
    onChange({ delay: next })
  }

  return (
    <div className="group relative rounded-lg border border-gray-200 bg-white transition-shadow hover:shadow-sm">
      {/* Step header bar */}
      <div className="flex items-center gap-3 border-b border-gray-100 px-4 py-2.5">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-gray-800 text-xs font-medium text-white">
          {stepNumber}
        </span>

        {isFirst ? (
          <span className="text-xs text-gray-500">Sends immediately</span>
        ) : (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-500">Wait</span>
            <input
              id={`step-${index}-delay`}
              type="number"
              min={1}
              value={step.delay}
              onChange={handleDelayChange}
              disabled={disabled}
              className="h-6 w-14 rounded border border-gray-200 px-1.5 text-center text-xs text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <span className="text-xs text-gray-500">min then send</span>
          </div>
        )}

        <div className="ml-auto flex items-center gap-1">
          {onMoveUp && index > 0 && (
            <button
              type="button"
              onClick={onMoveUp}
              disabled={disabled}
              className="rounded p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 disabled:opacity-40"
              aria-label="Move step up"
            >
              <ChevronUp size={14} />
            </button>
          )}
          {onMoveDown && index < totalSteps - 1 && (
            <button
              type="button"
              onClick={onMoveDown}
              disabled={disabled}
              className="rounded p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 disabled:opacity-40"
              aria-label="Move step down"
            >
              <ChevronDown size={14} />
            </button>
          )}
          {totalSteps > 1 && (
            <button
              type="button"
              onClick={onRemove}
              disabled={disabled}
              className="rounded p-1 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
              aria-label="Remove step"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Step body */}
      <div className="space-y-3 px-4 py-4">
        <div>
          <label htmlFor={`step-${index}-subject`} className="mb-1 block text-xs font-medium text-gray-500">
            Subject
          </label>
          <input
            id={`step-${index}-subject`}
            type="text"
            placeholder="Email subject line..."
            value={step.subject}
            onChange={(e) => onChange({ subject: e.target.value })}
            disabled={disabled}
            className="h-9 w-full rounded-md border border-gray-200 px-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            autoComplete="off"
          />
        </div>

        <div>
          <label htmlFor={`step-${index}-body`} className="mb-1 block text-xs font-medium text-gray-500">
            Body
          </label>
          <textarea
            id={`step-${index}-body`}
            placeholder="Write your email..."
            value={step.body_html}
            onChange={(e) => onChange({ body_html: e.target.value })}
            rows={5}
            disabled={disabled}
            className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      </div>
    </div>
  )
}
