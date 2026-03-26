import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { InboxReply, ReplyDetail, SentimentCounts } from '../lib/types'
import ReplyListItem from '../components/ReplyListItem'
import ThreadView from '../components/ThreadView'
import ReplyComposer from '../components/ReplyComposer'
import SentimentBadge from '../components/SentimentBadge'
import EmptyState from '../components/EmptyState'
import { Inbox } from 'lucide-react'

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'interested', label: 'Interested' },
  { key: 'not_interested', label: 'Not Interested' },
  { key: 'referral', label: 'Referral' },
  { key: 'neutral', label: 'Neutral' },
]

export default function InboxPage() {
  const [replies, setReplies] = useState<InboxReply[]>([])
  const [counts, setCounts] = useState<SentimentCounts | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReplyDetail | null>(null)
  const [activeTab, setActiveTab] = useState('all')
  const [loading, setLoading] = useState(true)
  const loadTokenRef = useRef(0)
  const detailTokenRef = useRef(0)

  const fetchReplies = useCallback((tab: string) => {
    const token = ++loadTokenRef.current
    Promise.all([
      api.inbox.replies(tab),
      api.inbox.counts(),
    ]).then(([repliesData, countsData]) => {
      if (loadTokenRef.current !== token) return
      setReplies(repliesData)
      setCounts(countsData)
      setLoading(false)
      if (repliesData.length > 0) {
        setSelectedId((prev) => prev ?? repliesData[0].id)
      }
    }).catch((err) => {
      console.error('Failed to load inbox replies', err)
      if (loadTokenRef.current === token) setLoading(false)
    })
  }, [])

  useEffect(() => {
    fetchReplies(activeTab)
  }, [activeTab, fetchReplies])

  const fetchDetail = useCallback((id: string) => {
    const token = ++detailTokenRef.current
    api.inbox.detail(id).then((data) => {
      if (detailTokenRef.current !== token) return
      setDetail(data)
    }).catch((err) => {
      console.error('Failed to load reply detail', err)
    })
  }, [])

  useEffect(() => {
    if (selectedId) {
      fetchDetail(selectedId)
    }
  }, [selectedId, fetchDetail])

  const handleTabChange = (tab: string) => {
    setActiveTab(tab)
    setSelectedId(null)
    setDetail(null)
    setLoading(true)
  }

  const handleSelectReply = (id: string) => {
    setSelectedId(id)
    setDetail(null)
  }

  const handleSendReply = async (bodyHtml: string) => {
    if (!selectedId) return
    try {
      await api.inbox.sendReply(selectedId, bodyHtml)
      const updated = await api.inbox.detail(selectedId)
      setDetail(updated)
    } catch (err) {
      console.error('Failed to send reply', err)
    }
  }

  if (loading) {
    return <div className="p-8 text-gray-400">Loading...</div>
  }

  const totalReplies = counts?.all ?? 0

  return (
    <div className="flex flex-col h-full">
      <div className="px-8 pt-8 pb-4">
        <h1 className="text-2xl font-semibold text-white mb-4">
          Inbox {totalReplies > 0 && <span className="text-gray-500">({totalReplies} replies)</span>}
        </h1>

        {totalReplies > 0 && (
          <div className="flex gap-2">
            {TABS.map((tab) => {
              const count = counts?.[tab.key as keyof SentimentCounts] ?? 0
              return (
                <button
                  key={tab.key}
                  onClick={() => handleTabChange(tab.key)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    activeTab === tab.key
                      ? 'bg-blue-500/20 text-blue-400 font-medium'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
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
        <div className="flex flex-1 min-h-0 mx-8 mb-8 bg-[#1E2235] rounded-xl border border-gray-700/50 overflow-hidden">
          <div className="w-[360px] border-r border-gray-700/50 overflow-y-auto">
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
                No {activeTab !== 'all' ? activeTab.replace('_', ' ') : ''} replies
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            {detail ? (
              <div>
                <div className="mb-6">
                  <h2 className="text-lg font-semibold text-white">{detail.candidate_name}</h2>
                  <p className="text-gray-400 text-sm">{detail.candidate_email}</p>
                  <p className="text-gray-500 text-xs mt-1">Sequence: {detail.sequence_name}</p>
                </div>

                {detail.sentiment && (
                  <div className="mb-6 p-3 bg-[#151827] rounded-lg border border-gray-700/30">
                    <div className="mb-1">
                      <SentimentBadge sentiment={detail.sentiment} size="md" />
                    </div>
                    {detail.sentiment_reasoning && (
                      <p className="text-gray-400 text-sm italic">"{detail.sentiment_reasoning}"</p>
                    )}
                  </div>
                )}

                <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">Thread</h3>
                <ThreadView thread={detail.thread} candidateName={detail.candidate_name} />

                <ReplyComposer onSend={handleSendReply} />
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
