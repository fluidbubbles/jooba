import type { ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiRequestError, api } from './api'
import { NylasConnectionContext, type NylasConnectionContextValue } from './nylasConnectionContext'
import type { NylasConnection } from './types'

function getStatusErrorMessage(err: unknown): string {
  if (err instanceof ApiRequestError) {
    if (err.status >= 500) {
      return 'Email connection status is temporarily unavailable.'
    }
    return err.message || 'Could not load email connection status.'
  }
  return 'Email connection status is temporarily unavailable.'
}

export default function NylasConnectionProvider({ children }: { children: ReactNode }) {
  const [connection, setConnectionState] = useState<NylasConnection | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestTokenRef = useRef(0)

  const refreshConnection = useCallback(async (): Promise<NylasConnection | null> => {
    const requestToken = requestTokenRef.current + 1
    requestTokenRef.current = requestToken
    setLoading(true)
    setError(null)

    try {
      const status = await api.nylas.status()
      if (requestToken !== requestTokenRef.current) {
        return null
      }
      setConnectionState(status)
      return status
    } catch (err) {
      console.error('Failed to load connection status', err)
      if (requestToken !== requestTokenRef.current) {
        return null
      }
      setError(getStatusErrorMessage(err))
      return null
    } finally {
      if (requestToken === requestTokenRef.current) {
        setLoading(false)
      }
    }
  }, [])

  const setConnection = useCallback((nextConnection: NylasConnection) => {
    requestTokenRef.current += 1
    setConnectionState(nextConnection)
    setError(null)
    setLoading(false)
  }, [])

  useEffect(() => {
    void refreshConnection()
  }, [refreshConnection])

  const value = useMemo<NylasConnectionContextValue>(
    () => ({
      connection,
      loading,
      error,
      refreshConnection,
      setConnection,
    }),
    [connection, loading, error, refreshConnection, setConnection]
  )

  return <NylasConnectionContext.Provider value={value}>{children}</NylasConnectionContext.Provider>
}
