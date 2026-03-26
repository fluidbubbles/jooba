import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import CreateSequence from './pages/CreateSequence'
import Dashboard from './pages/Dashboard'
import EditSequence from './pages/EditSequence'
import Inbox from './pages/Inbox'
import SequenceDetail from './pages/SequenceDetail'
import Sequences from './pages/Sequences'
import Settings from './pages/Settings'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/sequences" element={<Sequences />} />
        <Route path="/sequences/new" element={<CreateSequence />} />
        <Route path="/sequences/:id/edit" element={<EditSequence />} />
        <Route path="/sequences/:id" element={<SequenceDetail />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
