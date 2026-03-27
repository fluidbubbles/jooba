import { ChevronLeft, ChevronRight, MoreVertical, Search } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiRequestError } from '../lib/api'
import type { SequenceListItem, SequenceStatus } from '../lib/types'
import StatusBadge from './StatusBadge'

const PAGE_SIZE = 10

function formatCreatedAt(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

interface SequencesTableProps {
  statusFilter?: SequenceStatus
  sort?: string
}

export default function SequencesTable({ statusFilter, sort }: SequencesTableProps) {
  const navigate = useNavigate()
  const [items, setItems] = useState<SequenceListItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [menuOpen, setMenuOpen] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null)
  const [deleting, setDeleting] = useState(false)
  const loadRef = useRef(0)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(
    async (q: string, offset: number) => {
      const token = ++loadRef.current
      setLoading(true)
      setError(null)
      try {
        const data = await api.sequences.list({
          q: q || undefined,
          status: statusFilter,
          sort,
          limit: PAGE_SIZE,
          offset,
        })
        if (loadRef.current !== token) return
        setItems(data.items)
        setTotal(data.total)
      } catch (e) {
        console.error('Failed to load sequences:', e)
        if (loadRef.current !== token) return
        setError(e instanceof ApiRequestError ? e.message : 'Failed to load sequences')
      } finally {
        if (loadRef.current === token) setLoading(false)
      }
    },
    [statusFilter, sort],
  )

  const reload = useCallback(() => {
    void load(search, page * PAGE_SIZE)
  }, [load, search, page])

  useEffect(() => {
    reload()
  }, [reload])

  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPage(0)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      void load(value, 0)
    }, 300)
  }

  const handleStatusChange = async (id: string, status: SequenceStatus) => {
    setMenuOpen(null)
    try {
      await api.sequences.changeStatus(id, status)
      reload()
    } catch (err) {
      console.error('Failed to update sequence status', err)
      setError(err instanceof ApiRequestError ? err.message : 'Failed to update status')
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.sequences.delete(deleteTarget.id)
      setDeleteTarget(null)
      reload()
    } catch (err) {
      console.error('Failed to delete sequence', err)
      setError(err instanceof ApiRequestError ? err.message : 'Failed to delete sequence')
      setDeleteTarget(null)
    } finally {
      setDeleting(false)
    }
  }

  // Close menu when clicking outside
  useEffect(() => {
    if (!menuOpen) return
    const handler = () => setMenuOpen(null)
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [menuOpen])

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const showingFrom = total === 0 ? 0 : page * PAGE_SIZE + 1
  const showingTo = Math.min((page + 1) * PAGE_SIZE, total)

  return (
    <>
      {/* Delete confirmation */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-gray-900">Delete sequence?</h3>
            <p className="mt-2 text-sm text-gray-600">
              Are you sure you want to delete <strong>{deleteTarget.name}</strong>? This will also
              remove all enrollments and email history. This action cannot be undone.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                className="rounded-md px-4 py-2 text-sm font-medium text-gray-700 ring-1 ring-gray-300 hover:bg-gray-50"
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3"
        >
          <span className="text-[13px] text-red-800">{error}</span>
          <button
            type="button"
            onClick={reload}
            className="shrink-0 rounded-md bg-white px-3 py-1.5 text-[13px] font-medium text-red-800 ring-1 ring-red-200 transition-colors hover:bg-red-50"
          >
            Retry
          </button>
        </div>
      )}

      {/* Search bar */}
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Search sequences…"
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm text-gray-900 placeholder-gray-400 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
        />
      </div>

      {/* Loading */}
      {loading && items.length === 0 && (
        <div
          role="status"
          aria-live="polite"
          className="rounded-xl border border-gray-200 bg-white p-10 text-center text-sm text-gray-500 shadow-sm"
        >
          Loading sequences…
        </div>
      )}

      {/* Empty */}
      {!loading && !error && total === 0 && (
        <p className="py-8 text-center text-sm text-gray-500">
          {search ? 'No sequences match your search.' : 'No sequences yet.'}
        </p>
      )}

      {/* Table */}
      {items.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 text-left text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Name</th>
                  <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Status</th>
                  <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Steps</th>
                  <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Enrolled</th>
                  <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Replied</th>
                  <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">Created</th>
                  <th scope="col" className="w-10 py-3 pr-4"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {items.map((row) => (
                  <tr
                    key={row.id}
                    className="cursor-pointer transition-colors hover:bg-gray-50"
                    onClick={() => navigate(`/sequences/${row.id}`)}
                  >
                    <td className="whitespace-nowrap px-4 py-3 font-medium text-blue-600">
                      <Link to={`/sequences/${row.id}`} onClick={(e) => e.stopPropagation()}>
                        {row.name}
                      </Link>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">{row.step_count}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">{row.enrolled_count}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">{row.replied_count}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-600">{formatCreatedAt(row.created_at)}</td>
                    <td className="relative whitespace-nowrap py-3 pr-4 text-right">
                      <button
                        type="button"
                        aria-label="Sequence actions"
                        className="inline-flex items-center rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                        onClick={(e) => {
                          e.stopPropagation()
                          setMenuOpen(menuOpen === row.id ? null : row.id)
                        }}
                      >
                        <MoreVertical className="h-4 w-4" />
                      </button>
                      {menuOpen === row.id && (
                        <div className="absolute right-4 top-10 z-10 w-36 rounded-md border border-gray-200 bg-white py-1 shadow-lg">
                          {row.status === 'draft' && (
                            <button type="button" className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50" onClick={(e) => { e.stopPropagation(); void handleStatusChange(row.id, 'active') }}>
                              Activate
                            </button>
                          )}
                          {row.status === 'active' && (
                            <button type="button" className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50" onClick={(e) => { e.stopPropagation(); void handleStatusChange(row.id, 'paused') }}>
                              Pause
                            </button>
                          )}
                          {row.status === 'paused' && (
                            <>
                              <button type="button" className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50" onClick={(e) => { e.stopPropagation(); void handleStatusChange(row.id, 'active') }}>
                                Resume
                              </button>
                              <button type="button" className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50" onClick={(e) => { e.stopPropagation(); void handleStatusChange(row.id, 'archived') }}>
                                Archive
                              </button>
                            </>
                          )}
                          <button
                            type="button"
                            className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50"
                            onClick={(e) => { e.stopPropagation(); setMenuOpen(null); setDeleteTarget({ id: row.id, name: row.name }) }}
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-4 py-3 text-sm">
              <span className="text-gray-600">
                {showingFrom}–{showingTo} of {total}
              </span>
              <div className="flex gap-1">
                <button
                  type="button"
                  disabled={page === 0}
                  onClick={() => setPage(page - 1)}
                  className="inline-flex items-center rounded-md px-2 py-1 text-gray-600 hover:bg-gray-200 disabled:opacity-40 disabled:hover:bg-transparent"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage(page + 1)}
                  className="inline-flex items-center rounded-md px-2 py-1 text-gray-600 hover:bg-gray-200 disabled:opacity-40 disabled:hover:bg-transparent"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  )
}
