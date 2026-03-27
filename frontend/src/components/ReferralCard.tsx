import { CheckCircle, UserPlus, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getApiErrorMessage } from '../lib/api'
import type { ReferralInfo } from '../lib/types'
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
  const [dismissed, setDismissed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const loadTokenRef = useRef(0)

  const loadReferral = useCallback(async () => {
    const token = ++loadTokenRef.current
    setLoading(true)
    setError(null)
    try {
      const ref = await api.referrals.info(emailEventId)
      if (loadTokenRef.current !== token) return
      setReferral(ref)
    } catch (err) {
      console.error('Failed to load referral card data', err)
      if (loadTokenRef.current !== token) return
      setError(getApiErrorMessage(err, 'Failed to load referral data.'))
    } finally {
      if (loadTokenRef.current === token) setLoading(false)
    }
  }, [emailEventId])

  const retryReferral = useCallback(async () => {
    const token = ++loadTokenRef.current
    setLoading(true)
    setError(null)
    try {
      const ref = await api.referrals.retry(emailEventId)
      if (loadTokenRef.current !== token) return
      setReferral(ref)
    } catch (err) {
      console.error('Failed to retry referral extraction', err)
      if (loadTokenRef.current !== token) return
      setError(getApiErrorMessage(err, 'Failed to extract referral.'))
    } finally {
      if (loadTokenRef.current === token) setLoading(false)
    }
  }, [emailEventId])

  useEffect(() => {
    setDismissed(false)
    void loadReferral()
  }, [loadReferral])

  if (dismissed) {
    return null
  }

  if (loading && !referral && !error) {
    return null
  }

  if (!referral) {
    return (
      <ReferralCardShell onDismiss={() => setDismissed(true)}>
        {loading ? (
          <p className="text-sm text-gray-500">Retrying…</p>
        ) : error ? (
          <p role="alert" className="text-sm text-gray-700">
            {error}
          </p>
        ) : (
          <p className="text-sm text-gray-700">
            Referral details are not available for this reply yet.
          </p>
        )}
        {!loading && (
          <button
            type="button"
            onClick={() => void retryReferral()}
            className="mt-3 rounded-md border border-violet-300 bg-white px-3 py-1.5 text-sm font-medium text-violet-700 transition-colors hover:bg-violet-100"
          >
            Retry
          </button>
        )}
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

      {referral.enrolled ? (
        <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-emerald-700">
          <CheckCircle size={14} />
          Auto-enrolled into referral outreach sequence
        </p>
      ) : !referral.has_email ? (
        <p className="mt-3 text-xs text-amber-700">
          Email missing — cannot auto-enroll. Ask the referrer for the email.
        </p>
      ) : (
        <p className="mt-3 text-xs text-gray-500">
          Pending auto-enrollment into referral outreach sequence.
        </p>
      )}
    </ReferralCardShell>
  )
}
