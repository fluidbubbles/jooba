import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Inbox from './pages/Inbox'
import Sequences from './pages/Sequences'
import Settings from './pages/Settings'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/sequences" element={<Sequences />} />
        <Route
          path="/sequences/new"
          element={<div className="p-8 text-xl">Create Sequence (Plan 2)</div>}
        />
        <Route
          path="/sequences/:id"
          element={<div className="p-8 text-xl">Sequence Detail (Plan 3)</div>}
        />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Layout>
  )
}
