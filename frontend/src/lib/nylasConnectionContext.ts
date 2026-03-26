import { createContext, useContext } from 'react'

import type { NylasConnection } from './types'

export type NylasConnectionContextValue = {
  connection: NylasConnection | null
  loading: boolean
  error: string | null
  refreshConnection: () => Promise<NylasConnection | null>
  setConnection: (connection: NylasConnection) => void
}

export const NylasConnectionContext = createContext<NylasConnectionContextValue | null>(null)

export function useNylasConnection(): NylasConnectionContextValue {
  const context = useContext(NylasConnectionContext)
  if (!context) {
    throw new Error('useNylasConnection must be used within NylasConnectionProvider')
  }
  return context
}
