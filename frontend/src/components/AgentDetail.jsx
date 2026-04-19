export default function AgentDetail({ agent, history, onEdit, onDelete }) {
  const totalMessages = history.length
  const lastActive = history.length > 0
    ? new Date(history[history.length - 1].timestamp).toLocaleString()
    : 'Never'

  const toolsUsed = new Set()
  history.forEach(entry => {
    entry.activity?.forEach(a => {
      if (a.type === 'tool') toolsUsed.add(a.description)
    })
  })

  const TOOL_ICONS = {
    web_search: '🔍',
    wikipedia: '📖',
    code_interpreter: '💻',
    file_reader: '📄',
    calculator: '🧮',
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-xl font-bold" style={{ background: 'rgba(108,99,255,0.2)', border: '1px solid rgba(108,99,255,0.3)', color: '#6c63ff' }}>
            {agent.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">{agent.name}</h2>
            <p className="text-sm mt-0.5" style={{ color: '#9ca3af' }}>{agent.role}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-2.5 py-1 rounded-full text-xs font-medium`}
            style={{ background: agent.status === 'active' ? 'rgba(34,197,94,0.15)' : 'rgba(107,114,128,0.15)', color: agent.status === 'active' ? '#22c55e' : '#6b7280' }}>
            {agent.status}
          </span>
          <button
            onClick={onEdit}
            className="px-3 py-1.5 rounded-lg text-sm font-medium transition-all hover:opacity-90"
            style={{ background: '#6c63ff', color: 'white' }}
          >
            Edit
          </button>
          <button
            onClick={onDelete}
            className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
            style={{ border: '1px solid #ef4444', color: '#ef4444' }}
          >
            Delete
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        {[
          { label: 'Total Messages', value: totalMessages },
          { label: 'Tools Used', value: toolsUsed.size },
          { label: 'Last Active', value: lastActive, small: true },
        ].map(stat => (
          <div key={stat.label} className="rounded-xl p-4" style={{ background: '#0f1117', border: '1px solid #2a2d3e' }}>
            <p className="text-xs mb-1" style={{ color: '#6b7280' }}>{stat.label}</p>
            <p className={`font-semibold text-white ${stat.small ? 'text-xs' : 'text-xl'}`}>{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Instructions */}
      <Section title="System Instructions">
        <p className="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: '#d1d5db' }}>
          {agent.instructions || <span style={{ color: '#6b7280' }}>No instructions set</span>}
        </p>
      </Section>

      {/* Config */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <Section title="LLM Model">
          <span className="inline-block px-3 py-1.5 rounded-lg text-sm font-medium" style={{ background: 'rgba(108,99,255,0.15)', color: '#818cf8', border: '1px solid rgba(108,99,255,0.2)' }}>
            {agent.llm}
          </span>
        </Section>
        <Section title="Status">
          <span className="inline-flex items-center gap-2 text-sm" style={{ color: '#d1d5db' }}>
            <span className="w-2 h-2 rounded-full" style={{ background: agent.status === 'active' ? '#22c55e' : '#6b7280' }} />
            {agent.status}
          </span>
        </Section>
      </div>

      {/* Tools */}
      <Section title="Tools">
        {(agent.tools?.length ?? 0) === 0 ? (
          <p className="text-sm" style={{ color: '#6b7280' }}>No tools configured</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {(agent.tools || []).map(tool => (
              <span key={tool} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #2a2d3e', color: '#d1d5db' }}>
                <span>{TOOL_ICONS[tool] || '🔧'}</span>
                {tool}
              </span>
            ))}
          </div>
        )}
      </Section>

      {/* Connections */}
      {(agent.connections?.length ?? 0) > 0 && (
        <Section title="Connections">
          <div className="space-y-2">
            {(agent.connections || []).map((conn, i) => (
              <div key={i} className="flex items-center gap-2 text-sm px-3 py-2 rounded-lg" style={{ background: '#0f1117', border: '1px solid #2a2d3e', color: '#d1d5db' }}>
                <span style={{ color: '#6b7280' }}>→</span>
                {conn}
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="mb-4 rounded-xl p-4" style={{ background: '#0f1117', border: '1px solid #2a2d3e' }}>
      <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: '#6b7280' }}>{title}</h3>
      {children}
    </div>
  )
}
