import { useState, useRef, useEffect } from 'react'

function ActivityEntry({ item }) {
  const colorMap = {
    tool: '#3b82f6',
    success: '#22c55e',
    error: '#ef4444',
    message: '#6b7280',
  }
  const color = colorMap[item.type] || '#6b7280'
  const labels = { tool: 'TOOL', success: 'OK', error: 'ERR', message: 'MSG' }

  return (
    <div className="flex items-start gap-2 text-xs py-0.5">
      <span className="font-mono font-bold shrink-0" style={{ color }}>{labels[item.type] || 'LOG'}</span>
      <span style={{ color: '#94a3b8' }}>{item.description}</span>
    </div>
  )
}

function MessageBubble({ entry }) {
  const [expanded, setExpanded] = useState(false)
  const hasActivity = entry.activity && entry.activity.length > 0

  return (
    <div className="space-y-2 mb-4">
      {/* User message */}
      <div className="flex justify-end">
        <div className="max-w-[75%] px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm" style={{ background: '#6c63ff', color: 'white' }}>
          {entry.user_message}
        </div>
      </div>

      {/* Agent message */}
      <div className="flex justify-start flex-col">
        <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-tl-sm text-sm" style={{ background: '#1e2235', color: '#e2e8f0', border: '1px solid #2a2d3e' }}>
          <p className="whitespace-pre-wrap leading-relaxed">{entry.agent_response}</p>
        </div>

        {/* Activity collapsible */}
        {hasActivity && (
          <div className="mt-1.5 max-w-[80%]">
            <button
              onClick={() => setExpanded(v => !v)}
              className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-md transition-colors hover:bg-white/5"
              style={{ color: '#6b7280' }}
            >
              <svg className={`w-3 h-3 transition-transform ${expanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              Activity ({entry.activity.length} steps)
            </button>
            {expanded && (
              <div className="mt-1 px-3 py-2 rounded-lg space-y-0.5" style={{ background: '#0f1117', border: '1px solid #2a2d3e' }}>
                {entry.activity.map(a => <ActivityEntry key={a.id} item={a} />)}
              </div>
            )}
          </div>
        )}

        <p className="text-xs mt-1 ml-1" style={{ color: '#4b5563' }}>
          {new Date(entry.timestamp).toLocaleTimeString()}
        </p>
      </div>
    </div>
  )
}

export default function ChatPanel({ agent, history, loading, onSend, onClearHistory }) {
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, loading])

  const handleSubmit = (e) => {
    e.preventDefault()
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    onSend(msg)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Clear button */}
      <div className="flex justify-end px-4 py-2 shrink-0 border-b" style={{ borderColor: '#2a2d3e' }}>
        <button
          onClick={onClearHistory}
          className="text-xs px-3 py-1.5 rounded-lg transition-colors hover:bg-white/5"
          style={{ color: '#6b7280', border: '1px solid #2a2d3e' }}
        >
          Clear History
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {history.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center text-gray-500">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-3 text-2xl" style={{ background: 'rgba(108,99,255,0.15)', border: '1px solid rgba(108,99,255,0.3)' }}>
              🤖
            </div>
            <p className="font-medium text-gray-300">{agent.name}</p>
            <p className="text-sm mt-1">{agent.role}</p>
            <p className="text-xs mt-3 max-w-xs">Send a message to start the conversation</p>
          </div>
        )}
        {history.map(entry => <MessageBubble key={entry.id} entry={entry} />)}
        {loading && (
          <div className="flex justify-start mb-4">
            <div className="px-4 py-3 rounded-2xl rounded-tl-sm" style={{ background: '#1e2235', border: '1px solid #2a2d3e' }}>
              <div className="flex gap-1.5 items-center">
                <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: '#6c63ff', animationDelay: '0ms' }} />
                <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: '#6c63ff', animationDelay: '150ms' }} />
                <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: '#6c63ff', animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="px-4 py-3 shrink-0 border-t" style={{ borderColor: '#2a2d3e', background: '#1a1d27' }}>
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder={`Message ${agent.name}...`}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm outline-none transition-colors"
            style={{ background: '#0f1117', border: '1px solid #2a2d3e', color: '#e2e8f0' }}
            onFocus={e => e.target.style.borderColor = '#6c63ff'}
            onBlur={e => e.target.style.borderColor = '#2a2d3e'}
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-4 py-2.5 rounded-xl text-sm font-medium transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed active:scale-95"
            style={{ background: '#6c63ff', color: 'white' }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </div>
      </form>
    </div>
  )
}
