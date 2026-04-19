const TYPE_CONFIG = {
  tool: { color: '#3b82f6', bg: 'rgba(59,130,246,0.1)', label: 'TOOL', icon: '⚙️' },
  success: { color: '#22c55e', bg: 'rgba(34,197,94,0.1)', label: 'OK', icon: '✓' },
  error: { color: '#ef4444', bg: 'rgba(239,68,68,0.1)', label: 'ERR', icon: '✗' },
  message: { color: '#6b7280', bg: 'rgba(107,114,128,0.1)', label: 'MSG', icon: '●' },
}

function ActivityItem({ item }) {
  const cfg = TYPE_CONFIG[item.type] || TYPE_CONFIG.message
  return (
    <div className="flex items-start gap-2.5 py-2.5 border-b" style={{ borderColor: '#2a2d3e' }}>
      <div className="w-5 h-5 rounded flex items-center justify-center shrink-0 mt-0.5 text-xs font-bold" style={{ background: cfg.bg, color: cfg.color }}>
        {cfg.icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs leading-snug" style={{ color: '#d1d5db' }}>
          {item.description}
        </p>
        <p className="text-xs mt-0.5" style={{ color: '#4b5563' }}>
          {new Date(item.timestamp).toLocaleTimeString()}
        </p>
      </div>
    </div>
  )
}

export default function ActivityLog({ activity }) {
  return (
    <div className="flex flex-col h-full border-l" style={{ borderColor: '#2a2d3e' }}>
      <div className="px-4 py-3 border-b shrink-0" style={{ borderColor: '#2a2d3e' }}>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Activity Feed</h3>
          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(108,99,255,0.15)', color: '#818cf8' }}>
            {activity.length}
          </span>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
          {Object.entries(TYPE_CONFIG).map(([key, cfg]) => (
            <div key={key} className="flex items-center gap-1 text-xs" style={{ color: cfg.color }}>
              <span>{cfg.icon}</span>
              <span style={{ color: '#6b7280' }}>{key}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4">
        {activity.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-8" style={{ color: '#4b5563' }}>
            <div className="text-3xl mb-2 opacity-40">📋</div>
            <p className="text-xs">No activity yet.<br />Send a message to see logs.</p>
          </div>
        ) : (
          activity.map(item => <ActivityItem key={item.id} item={item} />)
        )}
      </div>
    </div>
  )
}
