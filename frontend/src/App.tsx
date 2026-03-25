import { Route, Routes } from 'react-router-dom'

function Placeholder({ title }: { title: string }) {
  return <div className="p-8 text-2xl font-semibold text-gray-900">{title}</div>
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Placeholder title="Dashboard" />} />
      <Route path="/sequences" element={<Placeholder title="Sequences" />} />
      <Route path="/inbox" element={<Placeholder title="Inbox" />} />
      <Route path="/settings" element={<Placeholder title="Settings" />} />
    </Routes>
  )
}
