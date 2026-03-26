import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, getApiErrorMessage } from '../lib/api'
import type { InboxReply, ReplyDetail, Sentiment, SentimentCounts } from '../lib/types'
import ReplyListItem from '../components/ReplyListItem'
import ThreadView from '../components/ThreadView'
import ReplyComposer from '../components/ReplyComposer'
import SentimentBadge from '../components/SentimentBadge'
import ReferralCard from '../components/ReferralCard'
import EmptyState from '../components/EmptyState'
import { Inbox } from 'lucide-react'

type InboxTab = Sentiment | 'all' | 'unreplied'

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'unreplied', label: 'Unreplied' },
  { key: 'interested', label: 'Interested' },
  { key: 'not_interested', label: 'Not Interested' },
  { key: 'referral', label: 'Referral' },
  { key: 'neutral', label: 'Neutral' },
] as const satisfies ReadonlyArray<{ key: InboxTab; label: string }>

const VALID_FILTER_TABS: ReadonlySet<string> = new Set(TABS.map((t) => t.key))

function isInboxTab(value: string): value is InboxTab {
  return VALID_FILTER_TABS.has(value)
}

function tabFromSearchParams(searchParams: URLSearchParams): InboxTab {
  const raw = searchParams.get('filter')
  if (raw && isInboxTab(raw)) {
    return raw
  }
  return 'all'
}

export default function InboxPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = tabFromSearchParams(searchParams)
  const [replies, setReplies] = useState<InboxReply[]>([])
  const [counts, setCounts] = useState<SentimentCounts | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReplyDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)
  const loadTokenRef = useRef(0)
  const detailTokenRef = useRef(0)
  const selectedIdRef = useRef<string | null>(null)

  const fetchReplies = useCallback((tab: InboxTab) => {
    const token = ++loadTokenRef.current
    setLoading(true)
    setListError(null)
    Promise.all([
      api.inbox.replies(tab),
      api.inbox.counts(),
    ]).then(([repliesData, countsData]) => {
      if (loadTokenRef.current !== token) return
      setReplies(repliesData)
      setCounts(countsData)
      setLoading(false)
      const currentSelected = selectedIdRef.current
      const nextSelected = currentSelected && repliesData.some((r) => r.id === currentSelected)
        ? currentSelected
        : (repliesData[0]?.id ?? null)
      if (nextSelected !== currentSelected) {
        setDetail(null)
        setDetailError(null)
        setSendError(null)
      }
      selectedIdRef.current = nextSelected
      setSelectedId(nextSelected)
    }).catch((err) => {
      console.error('Failed to load inbox replies', err)
      if (loadTokenRef.current === token) {
        setListError(getApiErrorMessage(err, 'Failed to load inbox. Check your connection and try again.'))
        setLoading(false)
      }
    })
  }, [])

  useEffect(() => {
    // Async fetch; state updates occur in promise callbacks, not synchronously in this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load inbox when tab (URL filter) changes
    fetchReplies(activeTab)
  }, [activeTab, fetchReplies])

  const fetchDetail = useCallback((id: string) => {
    const token = ++detailTokenRef.current
    setDetailError(null)
    api.inbox.detail(id).then((data) => {
      if (detailTokenRef.current !== token) return
      setDetail(data)
    }).catch((err) => {
      console.error('Failed to load reply detail', err)
      if (detailTokenRef.current === token) {
        setDetailError(getApiErrorMessage(err, 'Failed to load thread. Click to retry.'))
      }
    })
  }, [])

  useEffect(() => {
    selectedIdRef.current = selectedId
  }, [selectedId])

  useEffect(() => {
    if (selectedId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- load thread detail when selection changes
      fetchDetail(selectedId)
    }
  }, [selectedId, fetchDetail])

  const handleTabChange = (tab: InboxTab) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (tab === 'all') {
          next.delete('filter')
        } else {
          next.set('filter', tab)
        }
        return next
      },
      { replace: true },
    )
    setSelectedId(null)
    selectedIdRef.current = null
    detailTokenRef.current += 1
    setDetail(null)
    setDetailError(null)
    setSendError(null)
  }

  const handleSelectReply = (id: string) => {
    if (id === selectedIdRef.current) {
      return
    }
    setSelectedId(id)
    selectedIdRef.current = id
    detailTokenRef.current += 1
    setDetail(null)
    setDetailError(null)
    setSendError(null)
  }

  const handleSendReply = async (bodyHtml: string) => {
    const targetId = selectedIdRef.current
    if (!targetId) return
    setSendError(null)
    try {
      await api.inbox.sendReply(targetId, bodyHtml)
    } catch (err) {
      console.error('Failed to send reply', err)
      setSendError(getApiErrorMessage(err, 'Failed to send reply. Please try again.'))
      throw err
    }
    if (selectedIdRef.current !== targetId) {
      return
    }
    fetchDetail(targetId)
  }

  if (loading) {
    return <div className="p-8 text-gray-500">Loading...</div>
  }

  if (listError) {
    return (
      <div className="p-8">
        <p className="text-red-600 mb-4">{listError}</p>
        <button
          onClick={() => fetchReplies(activeTab)}
          className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white text-sm rounded-lg"
        >
          Retry
        </button>
      </div>
    )
  }

  const totalReplies = counts?.all ?? 0

  return (
    <div className="flex flex-col h-full">
      <div className="px-8 pt-8 pb-4">
        <h1 className="text-2xl font-semibold text-gray-900 mb-4">
          Inbox {totalReplies > 0 && <span className="text-gray-400">({totalReplies} replies)</span>}
        </h1>

        {totalReplies > 0 && (
          <div className="flex gap-2">
            {TABS.map((tab) => {
              const count = counts?.[tab.key as keyof SentimentCounts] ?? 0
              return (
                <button
                  key={tab.key}
                  onClick={() => handleTabChange(tab.key)}
                  className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                    activeTab === tab.key
                      ? 'bg-green-500 text-white font-medium'
                      : 'text-gray-500 border border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  {tab.label} ({count})
                </button>
              )
            })}
          </div>
        )}
      </div>

      {totalReplies === 0 && (
        <div className="px-8">
          <EmptyState
            icon={Inbox}
            title="No replies yet"
            description="Replies from candidates will appear here once your sequences start sending and people respond."
          />
        </div>
      )}

      {totalReplies > 0 && (
        <div className="flex flex-1 min-h-0 mx-8 mb-8 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="w-[360px] border-r border-gray-200 overflow-y-auto">
            {replies.map((reply) => (
              <ReplyListItem
                key={reply.id}
                reply={reply}
                isSelected={reply.id === selectedId}
                onClick={() => handleSelectReply(reply.id)}
              />
            ))}
            {replies.length === 0 && (
              <div className="p-6 text-center text-gray-500 text-sm">
                No {activeTab !== 'all' ? activeTab.replaceAll('_', ' ') : ''} replies
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            {selectedId && detail ? (
              <div>
                <div className="mb-6">
                  <h2 className="text-xl font-semibold text-gray-900">{detail.candidate_name}</h2>
                  <p className="text-sm text-gray-500 mt-1">
                    {detail.candidate_email}
                    <span className="mx-1.5">&middot;</span>
                    Sequence: {detail.sequence_name}
                    <span className="mx-1.5">&middot;</span>
                    Step {detail.current_step}/{detail.total_steps}
                  </p>
                </div>

                {detail.sentiment && (
                  <div className="mb-6">
                    <SentimentBadge
                      sentiment={detail.sentiment}
                      size="md"
                      variant="banner"
                      reasoning={detail.sentiment_reasoning}
                    />
                  </div>
                )}

                {detail.sentiment === 'referral' && (
                  <ReferralCard emailEventId={selectedId} />
                )}

                <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">Thread</h3>
                <ThreadView thread={detail.thread} candidateName={detail.candidate_name} />

                {sendError && (
                  <p className="text-red-600 text-sm mt-2">{sendError}</p>
                )}
                <ReplyComposer onSend={handleSendReply} />
              </div>
            ) : detailError && selectedId ? (
              <div className="flex flex-col items-center justify-center h-full gap-2">
                <p className="text-red-600 text-sm">{detailError}</p>
                <button
                  onClick={() => selectedId && fetchDetail(selectedId)}
                  className="text-blue-500 text-sm hover:underline"
                >
                  Retry
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500 text-sm">
                Select a reply to view the thread
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
