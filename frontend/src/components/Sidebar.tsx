import { Inbox, LayoutDashboard, Mail, Settings } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sequences', icon: Mail, label: 'Sequences' },
  { to: '/inbox', icon: Inbox, label: 'Inbox' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
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
      <div className="flex items-center gap-2">
        <div className="h-2 w-2 rounded-full bg-green-500" />
        <span className="text-xs text-gray-400">dan@ramp.com</span>
      </div>
    </aside>
  )
}
