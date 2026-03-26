import { ExternalLink, Mail, RotateCcw, Unplug } from 'lucide-react'
import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'

import { ApiRequestError, api } from '../lib/api'
import { useNylasConnection } from '../lib/nylasConnectionContext'
import type { NylasConnection } from '../lib/types'

const DISCONNECTED_CONNECTION: NylasConnection = {
  connected: false,
  email: null,
  provider: null,
  connected_at: null,
}

function getOAuthErrorMessage(errorCode: string): string {
  switch (errorCode) {
    case 'oauth_denied':
      return 'Email connection was cancelled. You can try again anytime.'
    case 'invalid_state':
      return 'Connection could not be verified. Please try connecting again.'
    case 'provider_rate_limited':
      return 'Email provider is rate limiting requests. Please retry shortly.'
    case 'auth_temporary':
      return 'Email provider is temporarily unavailable. Please retry shortly.'
    default:
      return 'Email connection failed. Please try again.'
  }
}

function getRequestErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiRequestError && err.message) {
    return err.message
  }
  return fallback
}

export default function Settings() {
  const { connection, loading, error: loadError, refreshConnection, setConnection } =
    useNylasConnection()
  const [disconnecting, setDisconnecting] = useState(false)
  const [awaitingOAuthStatus, setAwaitingOAuthStatus] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [statusTone, setStatusTone] = useState<'success' | 'error'>('success')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const connected = params.get('connected')
    const errorCode = params.get('error')

    if (connected === 'true') {
      setAwaitingOAuthStatus(true)
      void refreshConnection()
    } else if (errorCode) {
      setStatusTone('error')
      setStatusMessage(getOAuthErrorMessage(errorCode))
    }

    if (connected || errorCode) {
      const cleanPath = `${window.location.pathname}${window.location.hash}`
      window.history.replaceState({}, '', cleanPath)
    }
  }, [refreshConnection])

  useEffect(() => {
    if (!awaitingOAuthStatus || loading) {
      return
    }
    if (connection?.connected) {
      setStatusTone('success')
      setStatusMessage('Email connected successfully.')
    } else if (loadError) {
      setStatusTone('error')
      setStatusMessage(loadError)
    } else {
      setStatusTone('error')
      setStatusMessage('Email connection could not be confirmed. Please retry.')
    }
    setAwaitingOAuthStatus(false)
  }, [awaitingOAuthStatus, loading, connection, loadError])

  async function handleConnect() {
    try {
      const { url } = await api.nylas.authUrl()
      window.location.href = url
    } catch (err) {
      console.error('Failed to get auth URL', err)
      setStatusTone('error')
      setStatusMessage(getRequestErrorMessage(err, 'Could not start email connection.'))
    }
  }

  async function handleDisconnect() {
    setDisconnecting(true)
    try {
      await api.nylas.disconnect()
      setConnection(DISCONNECTED_CONNECTION)
      setStatusTone('success')
      setStatusMessage('Email disconnected.')
    } catch (err) {
      console.error('Failed to disconnect', err)
      setStatusTone('error')
      setStatusMessage(getRequestErrorMessage(err, 'Could not disconnect email account.'))
    } finally {
      setDisconnecting(false)
    }
  }

  const isConnected = connection?.connected === true && !loadError
  const connectedAt = connection?.connected_at

  if (awaitingOAuthStatus || (loading && !connection)) {
    return <div className="p-8 text-gray-400">Loading...</div>
  }

  let emailConnectionBody: ReactNode
  if (isConnected) {
    emailConnectionBody = (
      <div className="bg-[#151827] rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="w-2 h-2 rounded-full bg-green-400" />
              <span className="text-green-400 text-sm font-medium">Connected</span>
            </div>
            <p className="text-white">{connection?.email || 'Connected account'}</p>
            {connectedAt && (
              <p className="text-xs text-gray-500 mt-1">
                Connected on{' '}
                {new Date(connectedAt).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={handleDisconnect}
            disabled={disconnecting}
            className="flex items-center gap-2 px-3 py-2 border border-red-500/30 text-red-400 hover:bg-red-500/10 text-sm rounded-lg transition-colors disabled:opacity-40"
          >
            <Unplug size={14} />
            {disconnecting ? 'Disconnecting...' : 'Disconnect'}
          </button>
        </div>
      </div>
    )
  } else if (loadError) {
    emailConnectionBody = (
      <div className="text-center py-6">
        <div className="flex items-center gap-2 mb-3 justify-center">
          <span className="w-2 h-2 rounded-full bg-amber-400" />
          <span className="text-amber-300 text-sm font-medium">Status Unavailable</span>
        </div>
        <p className="text-gray-400 text-sm mb-4">
          We could not confirm your email connection status. Retry first, then reconnect if needed.
        </p>
        <div className="flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={() => void refreshConnection()}
            className="inline-flex items-center gap-2 px-4 py-2 border border-amber-400/40 text-amber-200 hover:bg-amber-500/15 text-sm rounded-lg transition-colors"
          >
            <RotateCcw size={14} />
            Retry
          </button>
          <button
            type="button"
            onClick={handleConnect}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <ExternalLink size={14} />
            Reconnect
          </button>
        </div>
      </div>
    )
  } else {
    emailConnectionBody = (
      <div className="text-center py-6">
        <div className="flex items-center gap-2 mb-3 justify-center">
          <span className="w-2 h-2 rounded-full bg-red-400" />
          <span className="text-red-400 text-sm font-medium">Not Connected</span>
        </div>
        <p className="text-gray-400 text-sm mb-4">
          Connect your email to send and receive messages through this app. Emails will come from your
          personal inbox — not from Jooba.
        </p>
        <button
          type="button"
          onClick={handleConnect}
          className="inline-flex items-center gap-2 px-6 py-2.5 bg-blue-500 hover:bg-blue-600 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <ExternalLink size={16} />
          Connect Email
        </button>
      </div>
    )
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-semibold text-white mb-8">Settings</h1>

      {statusMessage ? (
        <div
          className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
            statusTone === 'success'
              ? 'border-green-500/30 bg-green-500/10 text-green-300'
              : 'border-red-500/30 bg-red-500/10 text-red-300'
          }`}
        >
          {statusMessage}
        </div>
      ) : null}

      <div className="mb-8">
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">
          Email Connection
        </h2>

        <div className="bg-[#1E2235] rounded-xl border border-gray-700/50 p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-blue-500/10 rounded-lg flex items-center justify-center">
              <Mail size={20} className="text-blue-400" />
            </div>
            <div>
              <h3 className="text-white font-medium">Email Account</h3>
              <p className="text-xs text-gray-500">Send and receive through your personal inbox</p>
            </div>
          </div>

          {emailConnectionBody}
        </div>
      </div>
    </div>
  )
}
