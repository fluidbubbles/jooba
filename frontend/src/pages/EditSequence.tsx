import { ArrowLeft, Plus } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import StepEditor from '../components/StepEditor'
import { api, ApiRequestError } from '../lib/api'
import type { Sequence, SequenceUpdateInput, StepInput } from '../lib/types'

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

function buildUpdatePayload(
  name: string,
  steps: StepState[],
  meta: {
    role_title: string
    company: string
  },
): SequenceUpdateInput {
  const normalized = normalizeSteps(steps.map(toStepInput))
  return {
    name: name.trim(),
    steps: normalized,
    role_title: trimToOptional(meta.role_title) ?? null,
    company: trimToOptional(meta.company) ?? null,
  }
}

function sortedSteps(seq: Sequence): StepInput[] {
  return [...seq.steps]
    .sort((a, b) => a.step_order - b.step_order)
    .map((s) => ({
      subject: s.subject,
      body_html: s.body_html,
      delay: s.delay,
    }))
}

function apiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiRequestError ? error.message : fallback
}

function isOutdatedRequest(
  token: number,
  expectedRouteId: string,
  latestTokenRef: { current: number },
  activeRouteIdRef: { current: string | undefined },
): boolean {
  return latestTokenRef.current !== token || activeRouteIdRef.current !== expectedRouteId
}

export default function EditSequence() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [roleTitle, setRoleTitle] = useState('')
  const [company, setCompany] = useState('')
  const [steps, setSteps] = useState<StepState[]>([])
  const [loadedSequence, setLoadedSequence] = useState<Sequence | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const saveInFlightRef = useRef(false)
  const latestLoadRef = useRef(0)
  const latestSaveRef = useRef(0)
  const activeRouteIdRef = useRef<string | undefined>(id)

  useEffect(() => {
    activeRouteIdRef.current = id
    latestSaveRef.current += 1
    saveInFlightRef.current = false
    setLoadedSequence(null)
    setSaveError(null)
    setSteps([])
    setSaving(false)
  }, [id])

  const applySequenceToForm = useCallback((seq: Sequence) => {
    setName(seq.name)
    setRoleTitle(seq.role_title ?? '')
    setCompany(seq.company ?? '')
    const ordered = sortedSteps(seq)
    setSteps(
      ordered.map((s, i) => ({
        ...s,
        delay: i === 0 ? 0 : Math.max(1, s.delay),
        clientId: crypto.randomUUID(),
      })),
    )
  }, [])

  const loadSequence = useCallback(async () => {
    if (!id) return
    const loadToken = ++latestLoadRef.current
    setLoading(true)
    setLoadError(null)
    setSaveError(null)
    try {
      const data = await api.sequences.get(id)
      if (isOutdatedRequest(loadToken, id, latestLoadRef, activeRouteIdRef)) return
      setLoadedSequence(data)
      applySequenceToForm(data)
    } catch (e) {
      console.error('Failed to load sequence:', e)
      if (isOutdatedRequest(loadToken, id, latestLoadRef, activeRouteIdRef)) return
      setLoadedSequence(null)
      setLoadError(apiErrorMessage(e, 'Failed to load sequence'))
    } finally {
      if (!isOutdatedRequest(loadToken, id, latestLoadRef, activeRouteIdRef)) {
        setLoading(false)
      }
    }
  }, [applySequenceToForm, id])

  useEffect(() => {
    if (!id) return
    void loadSequence()
  }, [id, loadSequence])

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
        .map((s, i) => (i === 0 ? { ...s, delay: 0 } : { ...s, delay: Math.max(1, s.delay) })),
    )
  }, [])

  const addStep = useCallback(() => {
    setSteps((prev) => [...prev, stepState(1)])
  }, [])

  const runSave = useCallback(async () => {
    if (!id || !loadedSequence || loadedSequence.id !== id || saveInFlightRef.current) return
    const validationError = validateForm(name, steps.map(toStepInput))
    if (validationError) {
      setSaveError(validationError)
      return
    }

    saveInFlightRef.current = true
    const saveToken = ++latestSaveRef.current
    setSaveError(null)
    setSaving(true)
    try {
      const payload = buildUpdatePayload(name, steps, {
        role_title: roleTitle,
        company,
      })
      await api.sequences.update(id, payload)
      if (!isOutdatedRequest(saveToken, id, latestSaveRef, activeRouteIdRef)) {
        navigate(`/sequences/${id}`)
      }
    } catch (e) {
      console.error('Failed to save sequence:', e)
      if (!isOutdatedRequest(saveToken, id, latestSaveRef, activeRouteIdRef)) {
        setSaveError(apiErrorMessage(e, 'Something went wrong. Try again.'))
      }
    } finally {
      if (!isOutdatedRequest(saveToken, id, latestSaveRef, activeRouteIdRef)) {
        saveInFlightRef.current = false
        setSaving(false)
      }
    }
  }, [company, id, loadedSequence, name, navigate, roleTitle, steps])

  const isCurrentSequence = !!loadedSequence && loadedSequence.id === id
  const formDisabled = loading || saving || !!loadError || !isCurrentSequence
  const isDraft = isCurrentSequence && loadedSequence.status === 'draft'
  const fieldsDisabled = formDisabled || !isDraft
  const readOnlyReason =
    loadedSequence && !isDraft
      ? 'Only draft sequences can be edited.'
      : null

  if (!id) {
    return (
      <div className="mx-auto max-w-3xl space-y-6 p-8">
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Missing sequence id.
        </div>
        <Link
          to="/sequences"
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900"
        >
          <ArrowLeft size={15} aria-hidden />
          Back to sequences
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      {/* Header */}
      <div className="space-y-4">
        <Link
          to={`/sequences/${id}`}
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 transition-colors hover:text-gray-900"
        >
          <ArrowLeft size={15} aria-hidden />
          Back to sequence
        </Link>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <h1 className="text-2xl font-semibold text-gray-900">Edit sequence</h1>
          <button
            type="button"
            disabled={fieldsDisabled || steps.length === 0}
            onClick={() => void runSave()}
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save changes'}
          </button>
        </div>
      </div>

      {loadError && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3"
        >
          <span className="text-sm text-red-800">{loadError}</span>
          <button
            type="button"
            onClick={() => void loadSequence()}
            className="shrink-0 rounded-md bg-white px-3 py-1.5 text-sm font-medium text-red-800 ring-1 ring-red-200 transition-colors hover:bg-red-50"
          >
            Retry
          </button>
        </div>
      )}

      {readOnlyReason && (
        <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {readOnlyReason}
        </div>
      )}

      {saveError && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {saveError}
        </div>
      )}

      {loading && (
        <div role="status" aria-live="polite" className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-500">
          Loading sequence...
        </div>
      )}

      {!loading && !loadError && isCurrentSequence && (
        <>
          {/* Sequence details */}
          <div className="rounded-lg border border-gray-200 bg-white p-5">
            <div className="space-y-4">
              <div>
                <label htmlFor="edit-sequence-name" className="mb-1 block text-xs font-medium text-gray-500">
                  Sequence name <span className="text-red-500">*</span>
                </label>
                <input
                  id="edit-sequence-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={fieldsDisabled}
                  className="h-10 w-full rounded-md border border-gray-200 px-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  autoComplete="off"
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="edit-meta-role" className="mb-1 block text-xs font-medium text-gray-500">
                    Role title <span className="text-xs font-normal text-gray-400">(optional)</span>
                  </label>
                  <input
                    id="edit-meta-role"
                    type="text"
                    value={roleTitle}
                    onChange={(e) => setRoleTitle(e.target.value)}
                    disabled={fieldsDisabled}
                    className="h-9 w-full rounded-md border border-gray-200 px-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label htmlFor="edit-meta-company" className="mb-1 block text-xs font-medium text-gray-500">
                    Company <span className="text-xs font-normal text-gray-400">(optional)</span>
                  </label>
                  <input
                    id="edit-meta-company"
                    type="text"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    disabled={fieldsDisabled}
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
                disabled={fieldsDisabled}
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
                  disabled={fieldsDisabled}
                  onChange={(patch) => updateStep(index, patch)}
                  onRemove={() => removeStep(index)}
                />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
