import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Upload, X } from 'lucide-react'
import Papa from 'papaparse'
import { api, ApiRequestError } from '../lib/api'
import type { CandidateInput, EnrollResponse } from '../lib/types'

interface Props {
  sequenceId: string
  onClose: () => void
  onEnrolled: (result: EnrollResponse) => void
}

const ALIAS_MAP: Record<string, string[]> = {
  email: ['email', 'e-mail', 'email_address', 'emailaddress'],
  first_name: ['first_name', 'firstname', 'first'],
  last_name: ['last_name', 'lastname', 'last'],
  company: ['company', 'organization', 'org'],
  title: ['title', 'job_title', 'jobtitle', 'position'],
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function normalizeColumnName(value: string): string {
  return value.toLowerCase().trim()
}

function buildFieldLookup(fields: string[]): Map<string, string> {
  const lookup = new Map<string, string>()
  for (const field of fields) {
    const normalized = normalizeColumnName(field)
    if (!lookup.has(normalized)) {
      lookup.set(normalized, field)
    }
  }
  return lookup
}

function findRequiredColumn(fields: string[], aliases: string[]): string | null {
  for (const field of fields) {
    if (aliases.includes(normalizeColumnName(field))) {
      return field
    }
  }
  return null
}

function findColumnValue(
  row: Record<string, string>,
  fieldLookup: Map<string, string>,
  aliases: string[],
): string | null {
  for (const alias of aliases) {
    const column = fieldLookup.get(alias)
    if (!column) {
      continue
    }
    const value = row[column]?.trim()
    if (value) {
      return value
    }
  }
  return null
}

function isValidEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value)
}

export default function CsvUploadModal({ sequenceId, onClose, onEnrolled }: Props) {
  const [candidates, setCandidates] = useState<CandidateInput[]>([])
  const [fileName, setFileName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [enrolling, setEnrolling] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const modalRef = useRef<HTMLDivElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  const parseFile = useCallback((file: File) => {
    setError(null)
    setWarning(null)
    setFileName(file.name)

    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const fields = results.meta.fields || []
        const fieldLookup = buildFieldLookup(fields)
        const emailCol = findRequiredColumn(fields, ALIAS_MAP.email)

        if (!emailCol) {
          setError(
            `Could not find an "email" column. Found columns: ${fields.join(', ') || 'none'}`,
          )
          return
        }

        const rows: CandidateInput[] = []
        let invalidEmailRows = 0
        for (const row of results.data as Record<string, string>[]) {
          const email = row[emailCol]?.trim()
          if (!email) continue
          if (!isValidEmail(email)) {
            invalidEmailRows += 1
            continue
          }

          rows.push({
            email,
            first_name: findColumnValue(row, fieldLookup, ALIAS_MAP.first_name) || undefined,
            last_name: findColumnValue(row, fieldLookup, ALIAS_MAP.last_name) || undefined,
            company: findColumnValue(row, fieldLookup, ALIAS_MAP.company) || undefined,
            title: findColumnValue(row, fieldLookup, ALIAS_MAP.title) || undefined,
          })
        }

        if (rows.length === 0) {
          if (invalidEmailRows > 0) {
            setError(
              `No valid rows found. ${invalidEmailRows} row(s) had invalid email format.`,
            )
          } else {
            setError('No valid rows found. Make sure the CSV has at least one row with an email.')
          }
          return
        }

        setCandidates(rows)
        if (invalidEmailRows > 0) {
          setWarning(
            `${invalidEmailRows} row(s) were skipped because they had invalid email format.`,
          )
        }
      },
      error: (err) => {
        console.error('CSV parse error:', err)
        setError(`Could not parse this file: ${err.message ?? 'unknown error'}. Make sure it is a valid CSV.`)
      },
    })
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      const file = e.dataTransfer.files[0]
      if (file) parseFile(file)
    },
    [parseFile],
  )

  async function handleEnroll() {
    setEnrolling(true)
    setError(null)
    try {
      const result = await api.enrollments.enroll(sequenceId, candidates)
      onEnrolled(result)
    } catch (err: unknown) {
      console.error('Failed to enroll candidates:', err)
      if (err instanceof ApiRequestError && err.status === 422) {
        setError('Some candidate rows are invalid. Check emails and field values, then try again.')
      } else {
        setError(err instanceof ApiRequestError ? err.message : 'Failed to enroll candidates')
      }
    } finally {
      setEnrolling(false)
    }
  }

  useEffect(() => {
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeButtonRef.current?.focus()

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onClose()
        return
      }

      if (e.key !== 'Tab' || !modalRef.current) return

      const focusable = Array.from(
        modalRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]',
        ),
      ).filter((element) => {
        if (element.getAttribute('tabindex') === '-1') return false
        if (element.hasAttribute('disabled')) return false
        if (element.getAttribute('aria-hidden') === 'true') return false
        return element.getClientRects().length > 0
      })
      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (e.shiftKey && active === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      previousFocusRef.current?.focus()
    }
  }, [onClose])

  function reset() {
    setCandidates([])
    setFileName('')
    setError(null)
    setWarning(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="Enroll candidates from CSV"
        className="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Enroll Candidates</h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="text-gray-400 transition-colors hover:text-gray-600"
          >
            <X size={20} aria-hidden />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {warning && (
            <div
              role="status"
              className="mb-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3"
            >
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-500" />
              <p className="text-sm text-amber-800">{warning}</p>
            </div>
          )}

          {error && (
            <div role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-500" />
              <div>
                <p className="text-sm text-red-800">{error}</p>
                {candidates.length === 0 && (
                  <button
                    type="button"
                    onClick={reset}
                    className="mt-1 text-sm text-red-600 underline"
                  >
                    Try Another File
                  </button>
                )}
              </div>
            </div>
          )}

          {candidates.length === 0 && !error && (
            <>
              <button
                type="button"
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileRef.current?.click()}
                className="cursor-pointer rounded-xl border-2 border-dashed border-gray-300 p-10 text-center transition-colors hover:border-blue-400"
              >
                <Upload size={32} className="mx-auto mb-3 text-gray-400" />
                <p className="mb-1 text-gray-700">Drag & drop a CSV file here</p>
                <p className="text-sm text-gray-500">or click to browse</p>
                <p className="mt-4 text-xs text-gray-400">
                  Expected columns: email (required), first_name, last_name, company, title
                </p>
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".csv"
                tabIndex={-1}
                aria-hidden="true"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) parseFile(file)
                }}
              />
            </>
          )}

          {candidates.length > 0 && (
            <div>
              <p className="text-sm text-gray-600">
                Parsed{' '}
                <span className="font-medium text-gray-900">{candidates.length}</span>{' '}
                candidates from &quot;{fileName}&quot;
              </p>

              <div className="mt-3 overflow-hidden rounded-lg border border-gray-200">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50">
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Email</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">First</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Last</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Company</th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Title</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {candidates.slice(0, 5).map((c, i) => (
                      <tr key={i}>
                        <td className="px-4 py-2 text-gray-900">{c.email}</td>
                        <td className="px-4 py-2 text-gray-500">{c.first_name || '\u2014'}</td>
                        <td className="px-4 py-2 text-gray-500">{c.last_name || '\u2014'}</td>
                        <td className="px-4 py-2 text-gray-500">{c.company || '\u2014'}</td>
                        <td className="px-4 py-2 text-gray-500">{c.title || '\u2014'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {candidates.length > 5 && (
                  <div className="border-t border-gray-200 px-4 py-2 text-xs text-gray-400">
                    ... {candidates.length - 5} more
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {candidates.length > 0 && (
          <div className="flex items-center justify-end gap-3 border-t border-gray-200 px-6 py-4">
            <button
              type="button"
              onClick={reset}
              className="px-4 py-2 text-sm text-gray-600 transition-colors hover:text-gray-900"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleEnroll}
              disabled={enrolling}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-40"
            >
              {enrolling ? 'Enrolling...' : `Enroll ${candidates.length}`}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
