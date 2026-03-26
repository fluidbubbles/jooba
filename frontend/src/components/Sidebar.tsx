import { Inbox, LayoutDashboard, Mail, Settings } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'

import { api } from '../lib/api'
import type { NylasConnection } from '../lib/types'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sequences', icon: Mail, label: 'Sequences' },
  { to: '/inbox', icon: Inbox, label: 'Inbox' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  const [connection, setConnection] = useState<NylasConnection | null>(null)

  useEffect(() => {
    api.nylas.status().then(setConnection).catch((err: unknown) => {
      console.error('Failed to load connection status', err)
    })
  }, [])

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col justify-between bg-[#1A1D2E] p-5">
      <div className="space-y-8">
        <h1 className="text-[22px] font-bold tracking-tight text-white">Jooba</h1>
        <nav className="space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-500 font-medium text-white'
                    : 'text-gray-400 hover:text-gray-200'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
      {connection?.connected ? (
        <div className="flex items-center gap-2 text-xs">
          <span className="w-2 h-2 rounded-full bg-green-400" />
          <span className="text-gray-400 truncate">{connection.email}</span>
        </div>
      ) : (
        <Link
          to="/settings"
          className="flex items-center gap-2 text-xs text-red-400 hover:text-red-300"
        >
          <span className="w-2 h-2 rounded-full bg-red-400" />
          Connect Email
        </Link>
      )}
    </aside>
  )
}
