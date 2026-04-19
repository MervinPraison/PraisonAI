export default function Sidebar({ agents, selectedId, onSelect, onNewAgent, onClose }) {
  return (
    <div className="flex flex-col h-full" style={{ background: '#1a1d27', borderRight: '1px solid #2a2d3e' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b shrink-0" style={{ borderColor: '#2a2d3e' }}>
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white font-bold text-sm" style={{ background: '#6c63ff' }}>
            A
          </div>
          <span className="font-bold text-white text-lg tracking-tight">AgentOS</span>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-white/10 transition-colors md:hidden text-gray-400"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto py-2 px-2">
        <p className="px-2 py-1.5 text-xs font-semibold uppercase tracking-wider" style={{ color: '#6b7280' }}>
          Agents ({agents.length})
        </p>
        {agents.length === 0 ? (
          <div className="px-2 py-4 text-center text-sm text-gray-500">
            No agents yet.<br />Create your first one below.
          </div>
        ) : (
          agents.map(agent => (
            <button
              key={agent.id}
              onClick={() => onSelect(agent.id)}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all mb-0.5 group"
              style={{
                background: selectedId === agent.id ? 'rgba(108,99,255,0.15)' : 'transparent',
                borderLeft: selectedId === agent.id ? '2px solid #6c63ff' : '2px solid transparent',
              }}
            >
              <div
                className="w-2 h-2 rounded-full shrink-0 mt-0.5"
                style={{ background: agent.status === 'active' ? '#22c55e' : agent.status === 'auditing' ? '#f59e0b' : '#6b7280' }}
              />
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium truncate ${selectedId === agent.id ? 'text-white' : 'text-gray-300 group-hover:text-white'}`}>
                  {agent.name}
                </p>
                <p className="text-xs truncate mt-0.5" style={{ color: '#6b7280' }}>
                  {agent.model}
                </p>
              </div>
            </button>
          ))
        )}
      </div>

      {/* New agent button */}
      <div className="p-3 border-t shrink-0" style={{ borderColor: '#2a2d3e' }}>
        <button
          onClick={onNewAgent}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all hover:opacity-90 active:scale-95"
          style={{ background: '#6c63ff', color: 'white' }}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Agent
        </button>
      </div>
    </div>
  )
}
