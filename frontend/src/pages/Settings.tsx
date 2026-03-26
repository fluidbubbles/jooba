import { ExternalLink, Mail, Unplug } from 'lucide-react'
import { useEffect, useState } from 'react'

import { api } from '../lib/api'
import type { NylasConnection } from '../lib/types'

export default function Settings() {
  const [connection, setConnection] = useState<NylasConnection | null>(null)
  const [loading, setLoading] = useState(true)
  const [disconnecting, setDisconnecting] = useState(false)

  async function load() {
    try {
      const status = await api.nylas.status()
      setConnection(status)
    } catch (err) {
      console.error('Failed to load connection status', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleConnect = async () => {
    try {
      const { url } = await api.nylas.authUrl()
      window.location.href = url
    } catch (err) {
      console.error('Failed to get auth URL', err)
    }
  }

  const handleDisconnect = async () => {
    setDisconnecting(true)
    try {
      await api.nylas.disconnect()
      setConnection({ connected: false, email: null, provider: null, connected_at: null })
    } catch (err) {
      console.error('Failed to disconnect', err)
    } finally {
      setDisconnecting(false)
    }
  }

  if (loading) {
    return <div className="p-8 text-gray-400">Loading...</div>
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-semibold text-white mb-8">Settings</h1>

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

          {connection?.connected ? (
            <div className="bg-[#151827] rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="w-2 h-2 rounded-full bg-green-400" />
                    <span className="text-green-400 text-sm font-medium">Connected</span>
                  </div>
                  <p className="text-white">{connection.email}</p>
                  {connection.connected_at && (
                    <p className="text-xs text-gray-500 mt-1">
                      Connected on{' '}
                      {new Date(connection.connected_at).toLocaleDateString('en-US', {
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
          ) : (
            <div className="text-center py-6">
              <div className="flex items-center gap-2 mb-3 justify-center">
                <span className="w-2 h-2 rounded-full bg-red-400" />
                <span className="text-red-400 text-sm font-medium">Not Connected</span>
              </div>
              <p className="text-gray-400 text-sm mb-4">
                Connect your email to send and receive messages through this app. Emails will come
                from your personal inbox — not from Jooba.
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
          )}
        </div>
      </div>
    </div>
  )
}
