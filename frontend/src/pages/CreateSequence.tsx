import { Plus } from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import StepEditor from '../components/StepEditor'
import { api, ApiRequestError } from '../lib/api'
import type { SequenceCreateInput, StepInput } from '../lib/types'

type StepState = StepInput & { clientId: string }

function stepState(delay: number): StepState {
  return {
    subject: '',
    body_html: '',
    delay,
    clientId: crypto.randomUUID(),
  }
}

function toStepInput(row: StepState): StepInput {
  return { subject: row.subject, body_html: row.body_html, delay: row.delay }
}

function normalizeSteps(steps: StepInput[]): StepInput[] {
  return steps.map((s, i) => ({
    subject: s.subject.trim(),
    body_html: s.body_html.trim(),
    delay: i === 0 ? 0 : Math.max(1, Math.floor(Number.isFinite(s.delay) ? s.delay : 1)),
  }))
}

function trimToOptional(value: string): string | undefined {
  const t = value.trim()
  return t === '' ? undefined : t
}

function validateForm(name: string, steps: StepInput[]): string | null {
  if (name.trim() === '') {
    return 'Sequence name is required.'
  }
  for (const [i, s] of steps.entries()) {
    if (s.subject.trim() === '') {
      return `Step ${i + 1}: subject is required.`
    }
    if (s.body_html.trim() === '') {
      return `Step ${i + 1}: body is required.`
    }
  }
  return null
}

function buildCreatePayload(
  name: string,
  steps: StepState[],
  meta: {
    role_title: string
    company: string
  },
): SequenceCreateInput {
  const normalized = normalizeSteps(steps.map(toStepInput))
  const payload: SequenceCreateInput = {
    name: name.trim(),
    steps: normalized,
  }

  const role_title = trimToOptional(meta.role_title)
  if (role_title !== undefined) payload.role_title = role_title
  const company = trimToOptional(meta.company)
  if (company !== undefined) payload.company = company

  return payload
}

export default function CreateSequence() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [roleTitle, setRoleTitle] = useState('')
  const [company, setCompany] = useState('')
  const [steps, setSteps] = useState<StepState[]>([stepState(0)])
  const [createdSequenceId, setCreatedSequenceId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const saveInFlightRef = useRef(false)

  const updateStep = useCallback((index: number, patch: Partial<StepInput>) => {
    setSteps((prev) =>
      prev.map((s, i) => {
        if (i !== index) return s
        const next = { ...s, ...patch }
        if (i === 0) {
          return { ...next, delay: 0 }
        }
        if ('delay' in patch && patch.delay !== undefined) {
          return { ...next, delay: Math.max(1, Math.floor(patch.delay)) }
        }
        return next
      }),
    )
  }, [])

  const removeStep = useCallback((index: number) => {
    setSteps((prev) =>
      prev
        .filter((_, i) => i !== index)
        .map((s, i) =>
          i === 0 ? { ...s, delay: 0 } : { ...s, delay: Math.max(1, s.delay) },
        ),
    )
  }, [])

  const addStep = useCallback(() => {
    setSteps((prev) => [...prev, stepState(1)])
  }, [])

  const runSave = useCallback(
    async (mode: 'draft' | 'activate') => {
      if (saveInFlightRef.current) {
        return
      }

      setError(null)
      let sequenceIdForRun = createdSequenceId
      if (!sequenceIdForRun) {
        const validationError = validateForm(name, steps.map(toStepInput))
        if (validationError) {
          setError(validationError)
          return
        }
      }

      saveInFlightRef.current = true
      setSaving(true)
      try {
        if (!sequenceIdForRun) {
          const payload = buildCreatePayload(name, steps, {
            role_title: roleTitle,
            company,
          })
          const created = await api.sequences.create(payload)
          sequenceIdForRun = created.id
          setCreatedSequenceId(sequenceIdForRun)
        }

        if (mode === 'activate') {
          await api.sequences.changeStatus(sequenceIdForRun, 'active')
        }
        navigate(`/sequences/${sequenceIdForRun}`)
      } catch (e) {
        if (sequenceIdForRun) {
          setError('Sequence was saved as draft. Retry activation or open the draft from Sequences.')
        } else {
          setError(e instanceof ApiRequestError ? e.message : 'Something went wrong. Try again.')
        }
      } finally {
        saveInFlightRef.current = false
        setSaving(false)
      }
    },
    [company, createdSequenceId, name, navigate, roleTitle, steps],
  )

  return (
    <div className="space-y-6 p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <h1 className="text-[28px] font-semibold tracking-tight text-gray-900">Create sequence</h1>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={saving}
            onClick={() => void runSave('draft')}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-800 shadow-sm transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? 'Saving…' : 'Save draft'}
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => void runSave('activate')}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? 'Saving…' : 'Save & activate'}
          </button>
        </div>
      </div>

      {error ? (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800">
          {error}
        </div>
      ) : null}

      {saving ? (
        <div
          role="status"
          aria-live="polite"
          className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600 shadow-sm"
        >
          Saving sequence…
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,320px)]">
        <div className="space-y-6">
          <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-base font-semibold text-gray-900">Sequence</h2>
            <div className="space-y-2">
              <label htmlFor="sequence-name" className="block text-xs font-medium text-gray-600">
                Name <span className="text-red-600">*</span>
              </label>
              <input
                id="sequence-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={saving}
                className="h-10 w-full max-w-xl rounded-md border border-gray-200 px-3 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                autoComplete="off"
              />
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-gray-900">Steps</h2>
              <button
                type="button"
                onClick={addStep}
                disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-800 shadow-sm transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Plus size={14} aria-hidden />
                Add step
              </button>
            </div>

            <div className="space-y-2">
              {steps.map((row, index) => (
                <StepEditor
                  key={row.clientId}
                  index={index}
                  step={toStepInput(row)}
                  totalSteps={steps.length}
                  disabled={saving}
                  onChange={(patch) => updateStep(index, patch)}
                  onRemove={() => removeStep(index)}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm lg:sticky lg:top-8 lg:self-start">
          <h2 className="text-base font-semibold text-gray-900">Context (optional)</h2>
          <p className="text-sm text-gray-500">
            Used for personalization and AI-assisted copy. All fields are optional.
          </p>
          <div className="space-y-3">
            <div className="space-y-1">
              <label htmlFor="meta-role" className="block text-xs font-medium text-gray-600">
                Role title
              </label>
              <input
                id="meta-role"
                type="text"
                value={roleTitle}
                onChange={(e) => setRoleTitle(e.target.value)}
                disabled={saving}
                className="h-9 w-full rounded-md border border-gray-200 px-3 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="meta-company" className="block text-xs font-medium text-gray-600">
                Company
              </label>
              <input
                id="meta-company"
                type="text"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                disabled={saving}
                className="h-9 w-full rounded-md border border-gray-200 px-3 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
