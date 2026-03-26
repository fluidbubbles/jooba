import { useState } from 'react'
import { Send } from 'lucide-react'

interface Props {
  onSend: (bodyHtml: string) => Promise<void>
}

export default function ReplyComposer({ onSend }: Props) {
  const [body, setBody] = useState('')
  const [sending, setSending] = useState(false)

  const handleSend = async () => {
    if (!body.trim()) return
    setSending(true)
    try {
      await onSend(`<p>${body.replace(/\n/g, '</p><p>')}</p>`)
      setBody('')
    } catch (err) {
      console.error('Failed to send reply', err)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="border-t border-gray-700/50 pt-4 mt-4">
      <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-2">Reply</h3>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Type your reply..."
        rows={4}
        className="w-full px-3 py-2 bg-[#151827] border border-gray-600 rounded-lg text-white text-sm placeholder:text-gray-500 focus:border-blue-500 focus:outline-none resize-y mb-3"
      />
      <div className="flex justify-end">
        <button
          onClick={handleSend}
          disabled={!body.trim() || sending}
          className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Send size={14} />
          {sending ? 'Sending...' : 'Send Reply'}
        </button>
      </div>
    </div>
  )
}
