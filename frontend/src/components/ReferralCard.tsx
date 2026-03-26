import { UserPlus, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getApiErrorMessage } from '../lib/api'
import type { ReferralInfo, SequenceListItem } from '../lib/types'
import type { ReactNode } from 'react'

type ReferralCardProps = {
  emailEventId: string
}

type ReferralCardShellProps = {
  onDismiss: () => void
  children: ReactNode
}

function ReferralCardShell({ onDismiss, children }: ReferralCardShellProps) {
  return (
    <section aria-label="Extracted referral" className="my-4 rounded-lg border border-violet-200 bg-violet-50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <UserPlus size={16} className="text-violet-700" />
          <span className="text-sm font-medium text-violet-700">Extracted Referral</span>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-md p-1 text-gray-500 transition-colors hover:bg-white hover:text-gray-700"
          aria-label="Dismiss referral card"
        >
          <X size={16} />
        </button>
      </div>
      {children}
    </section>
  )
}

export default function ReferralCard({ emailEventId }: ReferralCardProps) {
  const [referral, setReferral] = useState<ReferralInfo | null>(null)
  const [sequences, setSequences] = useState<SequenceListItem[]>([])
  const [dismissed, setDismissed] = useState(false)
  const [enrolled, setEnrolled] = useState(false)
  const [enrolling, setEnrolling] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedSequenceId, setSelectedSequenceId] = useState('')
  const loadTokenRef = useRef(0)
  const enrollTokenRef = useRef(0)
  const emailEventIdRef = useRef(emailEventId)

  const loadReferral = useCallback(async () => {
    const token = ++loadTokenRef.current
    setLoading(true)
    setError(null)
    try {
      const [ref, sequenceRows] = await Promise.all([
        api.referrals.info(emailEventId),
        api.sequences.list(),
      ])
      if (loadTokenRef.current !== token) {
        return
      }
      setReferral(ref)
      setSequences(sequenceRows.filter((row) => row.status === 'active'))
    } catch (err) {
      console.error('Failed to load referral card data', err)
      if (loadTokenRef.current !== token) {
        return
      }
      setError(getApiErrorMessage(err, 'Failed to load referral data.'))
    } finally {
      if (loadTokenRef.current === token) {
        setLoading(false)
      }
    }
  }, [emailEventId])

  useEffect(() => {
    emailEventIdRef.current = emailEventId
  }, [emailEventId])

  useEffect(() => {
    setDismissed(false)
    setEnrolled(false)
    setEnrolling(false)
    setSelectedSequenceId('')
    enrollTokenRef.current += 1
    void loadReferral()
  }, [loadReferral])

  const handleEnroll = async () => {
    if (!selectedSequenceId || !referral?.has_email) {
      return
    }
    const targetEventId = emailEventIdRef.current
    const enrollToken = ++enrollTokenRef.current
    setEnrolling(true)
    setError(null)
    try {
      await api.referrals.enroll(targetEventId, selectedSequenceId)
      if (emailEventIdRef.current !== targetEventId) {
        return
      }
      setEnrolled(true)
    } catch (err) {
      console.error('Failed to enroll referral', err)
      if (emailEventIdRef.current !== targetEventId) {
        return
      }
      setError(getApiErrorMessage(err, 'Failed to enroll referral.'))
    } finally {
      if (enrollTokenRef.current === enrollToken) {
        setEnrolling(false)
      }
    }
  }

  if (dismissed || enrolled) {
    return null
  }

  if (loading) {
    return null
  }

  if (!referral) {
    return (
      <ReferralCardShell onDismiss={() => setDismissed(true)}>
        {error ? (
          <p role="alert" className="text-sm text-gray-700">
            {error}
          </p>
        ) : (
          <p className="text-sm text-gray-700">
            Referral details are not available for this reply yet.
          </p>
        )}
        <button
          type="button"
          onClick={() => void loadReferral()}
          className="mt-3 rounded-md border border-violet-300 bg-white px-3 py-1.5 text-sm font-medium text-violet-700 transition-colors hover:bg-violet-100"
        >
          Retry
        </button>
      </ReferralCardShell>
    )
  }

  return (
    <ReferralCardShell onDismiss={() => setDismissed(true)}>
      <div className="space-y-1 text-sm text-gray-700">
        <p>
          <span className="text-gray-500">Name:</span> {referral.name || '(not found)'}
        </p>
        <p>
          <span className="text-gray-500">Email:</span> {referral.email || '(not found)'}
        </p>
        {referral.title && (
          <p>
            <span className="text-gray-500">Title:</span> {referral.title}
          </p>
        )}
        {referral.company && (
          <p>
            <span className="text-gray-500">Company:</span> {referral.company}
          </p>
        )}
        <p className="pt-1 text-xs text-gray-500">
          Referred by {referral.referrer_name} ({referral.referrer_email})
        </p>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-xs text-red-700">
          {error}
        </p>
      )}

      {!referral.has_email ? (
        <p className="mt-3 text-xs text-amber-700">
          Email missing - cannot auto-enroll. Ask the referrer for the email.
        </p>
      ) : sequences.length === 0 ? (
        <p className="mt-3 text-xs text-gray-600">
          No active sequences available. Activate a sequence to enroll this referral.
        </p>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label htmlFor={`referral-sequence-${emailEventId}`} className="sr-only">
            Select active sequence
          </label>
          <select
            id={`referral-sequence-${emailEventId}`}
            value={selectedSequenceId}
            onChange={(event) => setSelectedSequenceId(event.target.value)}
            disabled={enrolling}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-violet-500 focus:outline-none"
          >
            <option value="">Select active sequence...</option>
            {sequences.map((sequence) => (
              <option key={sequence.id} value={sequence.id}>
                {sequence.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleEnroll}
            disabled={!selectedSequenceId || enrolling}
            className="rounded-md bg-violet-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-violet-300"
          >
            {enrolling ? 'Enrolling...' : 'Enroll'}
          </button>
        </div>
      )}
    </ReferralCardShell>
  )
}
