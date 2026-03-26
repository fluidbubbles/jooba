import type { ReactNode } from 'react'
import NylasConnectionProvider from '../lib/nylasConnection'
import Sidebar from './Sidebar'

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <NylasConnectionProvider>
      <div className="flex h-screen bg-[#F5F5F7]">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </NylasConnectionProvider>
  )
}
