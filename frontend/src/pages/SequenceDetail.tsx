import { ArrowLeft, Upload } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import CandidateDetailModal from '../components/CandidateDetailModal'
import CandidatesTable from '../components/CandidatesTable'
import CsvUploadModal from '../components/CsvUploadModal'
import StatCard from '../components/StatCard'
import StatusBadge from '../components/StatusBadge'
import { api, ApiRequestError } from '../lib/api'
import type { EnrollResponse, Sequence, SequenceAnalytics, SequenceStatus } from '../lib/types'

const BTN_PRIMARY =
  'rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60'
const BTN_SECONDARY =
  'rounded-md bg-white px-3 py-1.5 text-sm font-medium text-gray-800 ring-1 ring-gray-200 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60'
const ALERT_ERROR_PANEL = 'rounded-lg border border-red-200 bg-red-50 px-4 py-3'
const ALERT_ERROR_TEXT = 'text-[13px] text-red-800'

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

function sortedSteps(seq: Sequence) {
  return [...seq.steps].sort((a, b) => a.step_order - b.step_order)
}

function formatStepDelay(stepIndex: number, delay: number): string {
  const label = `${delay} min`
  if (stepIndex === 0) {
    return delay === 0 ? 'Sends immediately' : `Delay: ${label}`
  }
  return `Delay after previous: ${label}`
}

function bodyPlainText(bodyHtml: string): string {
  if (!bodyHtml.trim()) return ''
  const doc = new DOMParser().parseFromString(bodyHtml, 'text/html')
  return doc.body.textContent?.trim() ?? ''
}

function BackToSequences({ className }: { className: string }) {
  return (
    <Link to="/sequences" className={className}>
      <ArrowLeft size={16} aria-hidden />
      Back to sequences
    </Link>
  )
}

function SequenceStatusActions({
  status,
  busy,
  onEditDraft,
  onApply,
}: {
  status: SequenceStatus
  busy: boolean
  onEditDraft: () => void
  onApply: (next: SequenceStatus) => void
}) {
  switch (status) {
    case 'draft':
      return (
        <>
          <button type="button" className={BTN_SECONDARY} disabled={busy} onClick={onEditDraft}>
            Edit
          </button>
          <button type="button" className={BTN_PRIMARY} disabled={busy} onClick={() => onApply('active')}>
            Activate
          </button>
        </>
      )
    case 'active':
      return (
        <button type="button" className={BTN_PRIMARY} disabled={busy} onClick={() => onApply('paused')}>
          Pause
        </button>
      )
    case 'paused':
      return (
        <>
          <button type="button" className={BTN_PRIMARY} disabled={busy} onClick={() => onApply('active')}>
            Resume
          </button>
          <button type="button" className={BTN_SECONDARY} disabled={busy} onClick={() => onApply('archived')}>
            Archive
          </button>
        </>
      )
    case 'archived':
      return null
    default: {
      const _exhaustive: never = status
      void _exhaustive
      return null
    }
  }
}

export default function SequenceDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [sequence, setSequence] = useState<Sequence | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [statusBusy, setStatusBusy] = useState(false)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [analytics, setAnalytics] = useState<SequenceAnalytics | null>(null)
  const [enrollResult, setEnrollResult] = useState<EnrollResponse | null>(null)
  const [selectedEnrollmentId, setSelectedEnrollmentId] = useState<string | null>(null)
  const latestLoadRef = useRef(0)
  const latestStatusActionRef = useRef(0)
  const latestAnalyticsRefreshRef = useRef(0)
  const enrollToastTimerRef = useRef<number | null>(null)
  const activeRouteIdRef = useRef<string | undefined>(id)

  const clearEnrollToastTimer = useCallback(() => {
    if (enrollToastTimerRef.current !== null) {
      window.clearTimeout(enrollToastTimerRef.current)
      enrollToastTimerRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => {
      clearEnrollToastTimer()
    }
  }, [clearEnrollToastTimer])

  useEffect(() => {
    activeRouteIdRef.current = id
    latestStatusActionRef.current += 1
    latestAnalyticsRefreshRef.current += 1
    clearEnrollToastTimer()
    setSequence(null)
    setLoading(true)
    setLoadError(null)
    setStatusBusy(false)
    setActionError(null)
    setEnrollResult(null)
    setSelectedEnrollmentId(null)
  }, [id, clearEnrollToastTimer])

  const loadSequence = useCallback(async () => {
    if (!id) return
    const loadToken = ++latestLoadRef.current
    setLoading(true)
    setLoadError(null)
    try {
      const [data, analyticsData] = await Promise.all([
        api.sequences.get(id),
        api.enrollments.analytics(id),
      ])
      if (isOutdatedRequest(loadToken, id, latestLoadRef, activeRouteIdRef)) return
      setSequence(data)
      setAnalytics(analyticsData)
    } catch (e) {
      console.error('Failed to load sequence:', e)
      if (isOutdatedRequest(loadToken, id, latestLoadRef, activeRouteIdRef)) return
      setSequence(null)
      setLoadError(apiErrorMessage(e, 'Failed to load sequence'))
    } finally {
      if (!isOutdatedRequest(loadToken, id, latestLoadRef, activeRouteIdRef)) {
        setLoading(false)
      }
    }
  }, [id])

  useEffect(() => {
    if (!id) return
    void loadSequence()
  }, [id, loadSequence])

  const orderedSteps = useMemo(
    () => (sequence ? sortedSteps(sequence) : []),
    [sequence],
  )

  function handleEnrolled(result: EnrollResponse) {
    if (!id) return
    const targetId = id
    setEnrollResult(result)
    setShowUploadModal(false)
    setRefreshKey((k) => k + 1)

    const refreshToken = ++latestAnalyticsRefreshRef.current
    void api.enrollments.analytics(targetId).then((analyticsData) => {
      if (isOutdatedRequest(refreshToken, targetId, latestAnalyticsRefreshRef, activeRouteIdRef)) {
        return
      }
      setAnalytics(analyticsData)
    }).catch((e: unknown) => {
      console.error('Failed to refresh analytics:', e)
    })

    clearEnrollToastTimer()
    enrollToastTimerRef.current = window.setTimeout(() => {
      setEnrollResult(null)
      enrollToastTimerRef.current = null
    }, 5000)
  }

  async function applyStatus(next: SequenceStatus) {
    if (!id || sequence?.id !== id) return
    const targetId = id
    const actionToken = ++latestStatusActionRef.current
    setActionError(null)
    setStatusBusy(true)
    try {
      const updated = await api.sequences.changeStatus(targetId, next)
      if (!isOutdatedRequest(actionToken, targetId, latestStatusActionRef, activeRouteIdRef)) {
        setSequence(updated)
      }
    } catch (e) {
      console.error('Failed to update status:', e)
      if (!isOutdatedRequest(actionToken, targetId, latestStatusActionRef, activeRouteIdRef)) {
        setActionError(apiErrorMessage(e, 'Failed to update status'))
      }
    } finally {
      if (!isOutdatedRequest(actionToken, targetId, latestStatusActionRef, activeRouteIdRef)) {
        setStatusBusy(false)
      }
    }
  }

  const closeCandidateDetailModal = useCallback(() => {
    setSelectedEnrollmentId(null)
  }, [])

  if (!id) {
    return (
      <div className="space-y-6 p-8">
        <div role="alert" className={`${ALERT_ERROR_PANEL} ${ALERT_ERROR_TEXT}`}>
          Missing sequence id.
        </div>
        <BackToSequences className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-700" />
      </div>
    )
  }

  return (
    <div className="space-y-6 p-8">
      <div className="flex flex-col gap-4">
        <BackToSequences className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-gray-600 transition-colors hover:text-gray-900" />

        {loadError && (
          <div
            role="alert"
            className={`flex flex-wrap items-center justify-between gap-3 ${ALERT_ERROR_PANEL}`}
          >
            <span className={ALERT_ERROR_TEXT}>{loadError}</span>
            <button
              type="button"
              onClick={() => void loadSequence()}
              className="shrink-0 rounded-md bg-white px-3 py-1.5 text-[13px] font-medium text-red-800 ring-1 ring-red-200 transition-colors hover:bg-red-50"
            >
              Retry
            </button>
          </div>
        )}

        {actionError && (
          <div role="alert" className={`${ALERT_ERROR_PANEL} ${ALERT_ERROR_TEXT}`}>
            {actionError}
          </div>
        )}

        {loading && (
          <div
            role="status"
            aria-live="polite"
            className="rounded-xl border border-gray-200 bg-white p-10 text-center text-sm text-gray-500 shadow-sm"
          >
            Loading sequence…
          </div>
        )}

        {!loading && !loadError && sequence && sequence.id === id && (
          <>
            <div className="flex flex-col gap-4 border-b border-gray-200 pb-6 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-[28px] font-semibold tracking-tight text-gray-900">{sequence.name}</h1>
                <StatusBadge status={sequence.status} />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {sequence.status === 'active' && (
                  <button
                    type="button"
                    className={BTN_SECONDARY}
                    onClick={() => setShowUploadModal(true)}
                  >
                    <Upload size={14} className="mr-1.5 inline" aria-hidden="true" />
                    Upload CSV
                  </button>
                )}
                <SequenceStatusActions
                  status={sequence.status}
                  busy={statusBusy}
                  onEditDraft={() => navigate(`/sequences/${sequence.id}/edit`)}
                  onApply={(next) => void applyStatus(next)}
                />
              </div>
            </div>

            {enrollResult && (
              <div role="alert" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-[13px] text-green-800">
                Enrolled {enrollResult.enrolled} candidate{enrollResult.enrolled !== 1 ? 's' : ''}.
                {enrollResult.skipped > 0 && ` ${enrollResult.skipped} already enrolled (skipped).`}
              </div>
            )}

            <section aria-label="Sequence analytics">
              <h2 className="sr-only">Analytics</h2>
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
                <StatCard label="Enrolled" value={analytics?.enrolled ?? 0} />
                <StatCard label="Sent" value={analytics?.sent ?? 0} />
                <StatCard label="Replied" value={analytics?.replied ?? 0} />
                <StatCard label="Interested" value={analytics?.interested ?? 0} accent />
                <StatCard label="Bounced" value={analytics?.bounced ?? 0} />
              </div>
            </section>

            <section aria-labelledby="steps-heading">
              <h2 id="steps-heading" className="mb-4 text-lg font-semibold text-gray-900">
                Steps
              </h2>
              <ol className="relative space-y-0 border-l border-gray-200 pl-6">
                {orderedSteps.map((step, index) => {
                  const plain = bodyPlainText(step.body_html)
                  return (
                    <li key={step.id} className="relative mb-8 ml-1 last:mb-0">
                      <span
                        className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full border border-white bg-blue-500 ring-2 ring-gray-100"
                        aria-hidden
                      />
                      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
                        <div className="border-b border-gray-100 bg-gray-50 px-4 py-2">
                          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                            Step {index + 1}
                            <span className="mx-2 text-gray-300">·</span>
                            {formatStepDelay(index, step.delay)}
                          </p>
                          <p className="mt-1 text-sm font-semibold text-gray-900">{step.subject || '(No subject)'}</p>
                        </div>
                        <div className="px-4 py-3 text-sm leading-relaxed text-gray-700">
                          {plain ? (
                            <p className="whitespace-pre-wrap">{plain}</p>
                          ) : (
                            <p className="text-gray-400">(No body)</p>
                          )}
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ol>
            </section>

            <section aria-labelledby="candidates-heading">
              <h2 id="candidates-heading" className="mb-4 text-lg font-semibold text-gray-900">
                Candidates
              </h2>
              <CandidatesTable
                sequenceId={id}
                onUploadCsv={
                  sequence.status === 'active' ? () => setShowUploadModal(true) : undefined
                }
                refreshKey={refreshKey}
                onRowClick={(enrollmentId) => setSelectedEnrollmentId(enrollmentId)}
              />
            </section>
          </>
        )}
      </div>

      {showUploadModal && (
        <CsvUploadModal
          sequenceId={id}
          onClose={() => setShowUploadModal(false)}
          onEnrolled={handleEnrolled}
        />
      )}

      {selectedEnrollmentId && (
        <CandidateDetailModal
          enrollmentId={selectedEnrollmentId}
          onClose={closeCandidateDetailModal}
        />
      )}
    </div>
  )
}
