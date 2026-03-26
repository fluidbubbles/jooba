const SENTIMENT_STYLES: Record<string, { dot: string; text: string; label: string }> = {
  interested: { dot: 'bg-green-400', text: 'text-green-400', label: 'Interested' },
  not_interested: { dot: 'bg-red-400', text: 'text-red-400', label: 'Not Interested' },
  referral: { dot: 'bg-purple-400', text: 'text-purple-400', label: 'Referral' },
  neutral: { dot: 'bg-gray-400', text: 'text-gray-400', label: 'Neutral' },
}

interface Props {
  sentiment: string | null
  size?: 'sm' | 'md'
}

export default function SentimentBadge({ sentiment, size = 'sm' }: Props) {
  if (!sentiment) return <span className="text-gray-600 text-xs">Classifying...</span>
  const style = SENTIMENT_STYLES[sentiment] ?? SENTIMENT_STYLES.neutral
  const dotSize = size === 'md' ? 'w-2.5 h-2.5' : 'w-2 h-2'
  const textSize = size === 'md' ? 'text-sm' : 'text-xs'
  return (
    <span className={`inline-flex items-center gap-1.5 ${textSize} ${style.text}`}>
      <span className={`${dotSize} rounded-full ${style.dot}`} />
      {style.label}
    </span>
  )
}
