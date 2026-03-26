const SENTIMENT_STYLES: Record<string, { dot: string; text: string; label: string; bg: string }> = {
  interested: { dot: 'bg-green-500', text: 'text-green-700', label: 'Interested', bg: 'bg-green-50' },
  not_interested: { dot: 'bg-red-500', text: 'text-red-700', label: 'Not Interested', bg: 'bg-red-50' },
  referral: { dot: 'bg-purple-500', text: 'text-purple-700', label: 'Referral', bg: 'bg-purple-50' },
  neutral: { dot: 'bg-gray-400', text: 'text-gray-600', label: 'Neutral', bg: 'bg-gray-50' },
}

interface Props {
  sentiment: string | null
  size?: 'sm' | 'md'
  variant?: 'inline' | 'banner'
  reasoning?: string | null
}

export default function SentimentBadge({ sentiment, size = 'sm', variant = 'inline', reasoning }: Props) {
  if (!sentiment) return <span className="text-gray-500 text-xs">Classifying...</span>
  const style = SENTIMENT_STYLES[sentiment] ?? SENTIMENT_STYLES.neutral
  const dotSize = size === 'md' ? 'w-2.5 h-2.5' : 'w-2 h-2'
  const textSize = size === 'md' ? 'text-sm' : 'text-xs'

  if (variant === 'banner') {
    return (
      <div className={`flex items-start gap-2 px-3 py-2 rounded-lg ${style.bg}`}>
        <span className={`inline-flex items-center gap-1.5 ${textSize} font-medium ${style.text} shrink-0 mt-0.5`}>
          <span className={`${dotSize} rounded-full ${style.dot}`} />
          {style.label}
        </span>
        {reasoning && (
          <span className={`${textSize} text-gray-600`}>
            &mdash; {reasoning}
          </span>
        )}
      </div>
    )
  }

  return (
    <span className={`inline-flex items-center gap-1.5 ${textSize} ${style.text}`}>
      <span className={`${dotSize} rounded-full ${style.dot}`} />
      {style.label}
    </span>
  )
}
