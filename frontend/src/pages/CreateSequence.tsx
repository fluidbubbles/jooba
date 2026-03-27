import { ArrowLeft, Plus } from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
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
        console.error('Failed to save sequence:', e)
        if (sequenceIdForRun) {
          const detail = e instanceof ApiRequestError ? ` ${e.message}` : ''
          setError(`Sequence was saved as draft, but activation failed.${detail} Retry activation or open the draft from Sequences.`)
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
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      {/* Header */}
      <div className="space-y-4">
        <Link
          to="/sequences"
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 transition-colors hover:text-gray-900"
        >
          <ArrowLeft size={15} aria-hidden />
          Sequences
        </Link>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <h1 className="text-2xl font-semibold text-gray-900">New sequence</h1>
          <button
            type="button"
            disabled={saving}
            onClick={() => void runSave('draft')}
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* Sequence details */}
      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <div className="space-y-4">
          <div>
            <label htmlFor="sequence-name" className="mb-1 block text-xs font-medium text-gray-500">
              Sequence name <span className="text-red-500">*</span>
            </label>
            <input
              id="sequence-name"
              type="text"
              placeholder="e.g. Senior Engineer Outreach"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={saving}
              className="h-10 w-full rounded-md border border-gray-200 px-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              autoComplete="off"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="meta-role" className="mb-1 block text-xs font-medium text-gray-500">
                Role title <span className="text-xs font-normal text-gray-400">(optional)</span>
              </label>
              <input
                id="meta-role"
                type="text"
                placeholder="e.g. Backend Engineer"
                value={roleTitle}
                onChange={(e) => setRoleTitle(e.target.value)}
                disabled={saving}
                className="h-9 w-full rounded-md border border-gray-200 px-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label htmlFor="meta-company" className="mb-1 block text-xs font-medium text-gray-500">
                Company <span className="text-xs font-normal text-gray-400">(optional)</span>
              </label>
              <input
                id="meta-company"
                type="text"
                placeholder="e.g. Acme Corp"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                disabled={saving}
                className="h-9 w-full rounded-md border border-gray-200 px-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">
            Steps <span className="ml-1 font-normal text-gray-400">({steps.length})</span>
          </h2>
          <button
            type="button"
            onClick={addStep}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus size={14} aria-hidden />
            Add step
          </button>
        </div>

        <div className="space-y-3">
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
  )
}
