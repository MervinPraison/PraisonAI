import { useState, useEffect, useCallback } from 'react'
import Sidebar from './components/Sidebar'
import ChatPanel from './components/ChatPanel'
import AgentDetail from './components/AgentDetail'
import ActivityLog from './components/ActivityLog'
import AgentForm from './components/AgentForm'

const API = '/api'

export default function App() {
  const [agents, setAgents] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [activeTab, setActiveTab] = useState('chat')
  const [showForm, setShowForm] = useState(false)
  const [editingAgent, setEditingAgent] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [history, setHistory] = useState([])
  const [activity, setActivity] = useState([])
  const [loading, setLoading] = useState(false)

  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch(`${API}/agents`)
      const data = await res.json()
      setAgents(data)
      if (!selectedId && data.length > 0) setSelectedId(data[0].id)
    } catch (e) {
      console.error('Failed to fetch agents', e)
    }
  }, [selectedId])

  const fetchHistory = useCallback(async (id) => {
    if (!id) return
    try {
      const res = await fetch(`${API}/agents/${id}/history`)
      setHistory(await res.json())
    } catch (e) { console.error(e) }
  }, [])

  const fetchActivity = useCallback(async (id) => {
    if (!id) return
    try {
      const res = await fetch(`${API}/agents/${id}/activity`)
      setActivity(await res.json())
    } catch (e) { console.error(e) }
  }, [])

  useEffect(() => { fetchAgents() }, [])

  useEffect(() => {
    if (selectedId) {
      fetchHistory(selectedId)
      fetchActivity(selectedId)
    }
  }, [selectedId])

  const handleSelectAgent = (id) => {
    setSelectedId(id)
    setActiveTab('chat')
  }

  const reportError = async (res, action) => {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* body may be empty */ }
    const msg = `${action} failed (${res.status})${detail ? `: ${detail}` : ''}`
    console.error(msg)
    window.alert(msg)
  }

  const handleSendMessage = async (message) => {
    if (!selectedId) return
    setLoading(true)
    try {
      const res = await fetch(`${API}/agents/${selectedId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      if (!res.ok) { await reportError(res, 'Send message'); return }
      const entry = await res.json()
      setHistory(prev => [...prev, entry])
      setActivity(prev => [...entry.activity, ...prev])
    } catch (e) {
      console.error(e)
      window.alert('Network error while sending message.')
    } finally {
      setLoading(false)
    }
  }

  const handleClearHistory = async () => {
    if (!selectedId) return
    const res = await fetch(`${API}/agents/${selectedId}/history`, { method: 'DELETE' })
    if (!res.ok) { await reportError(res, 'Clear history'); return }
    setHistory([])
    setActivity([])
  }

  const handleSaveAgent = async (data) => {
    if (editingAgent) {
      const res = await fetch(`${API}/agents/${editingAgent.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (!res.ok) { await reportError(res, 'Update agent'); return }
      const updated = await res.json()
      setAgents(prev => prev.map(a => a.id === updated.id ? updated : a))
    } else {
      const res = await fetch(`${API}/agents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (!res.ok) { await reportError(res, 'Create agent'); return }
      const created = await res.json()
      setAgents(prev => [...prev, created])
      setSelectedId(created.id)
    }
    setShowForm(false)
    setEditingAgent(null)
  }

  const handleDeleteAgent = async (id) => {
    if (!window.confirm('Delete this agent?')) return
    const res = await fetch(`${API}/agents/${id}`, { method: 'DELETE' })
    if (!res.ok) { await reportError(res, 'Delete agent'); return }
    setAgents(prev => prev.filter(a => a.id !== id))
    if (selectedId === id) {
      const remaining = agents.filter(a => a.id !== id)
      setSelectedId(remaining.length > 0 ? remaining[0].id : null)
    }
  }

  const selectedAgent = agents.find(a => a.id === selectedId)

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#0f1117' }}>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/50 z-10 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <div className={`
        fixed md:relative z-20 h-full transition-transform duration-300
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
        ${sidebarOpen ? 'w-64' : 'w-0 md:w-64'}
      `}>
        <Sidebar
          agents={agents}
          selectedId={selectedId}
          onSelect={handleSelectAgent}
          onNewAgent={() => { setEditingAgent(null); setShowForm(true) }}
          onClose={() => setSidebarOpen(false)}
        />
      </div>

      {/* Main content */}
      <div className="flex flex-1 min-w-0 overflow-hidden">
        {/* Center panel */}
        <div className="flex flex-col flex-1 min-w-0 overflow-hidden border-x" style={{ borderColor: '#2a2d3e' }}>
          {/* Header */}
          <div className="flex items-center px-4 py-3 border-b shrink-0" style={{ background: '#1a1d27', borderColor: '#2a2d3e' }}>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="mr-3 p-1.5 rounded-lg hover:bg-white/10 transition-colors md:hidden"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            {selectedAgent ? (
              <>
                <div className="flex items-center gap-2 flex-1">
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ background: selectedAgent.status === 'active' ? '#22c55e' : selectedAgent.status === 'auditing' ? '#f59e0b' : '#6b7280' }} />
                  <span className="font-semibold truncate">{selectedAgent.name}</span>
                  <span className="text-sm text-gray-400 truncate hidden sm:block">— {selectedAgent.model}</span>
                </div>
                <div className="flex gap-1 ml-2">
                  <button
                    onClick={() => setActiveTab('chat')}
                    className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${activeTab === 'chat' ? 'text-white' : 'text-gray-400 hover:text-white'}`}
                    style={activeTab === 'chat' ? { background: '#6c63ff' } : {}}
                  >Chat</button>
                  <button
                    onClick={() => setActiveTab('details')}
                    className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${activeTab === 'details' ? 'text-white' : 'text-gray-400 hover:text-white'}`}
                    style={activeTab === 'details' ? { background: '#6c63ff' } : {}}
                  >Details</button>
                </div>
              </>
            ) : (
              <span className="text-gray-400 text-sm">No agent selected</span>
            )}
          </div>

          {/* Panel content */}
          <div className="flex-1 overflow-hidden">
            {!selectedAgent ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-500">
                <svg className="w-16 h-16 mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2h-2" />
                </svg>
                <p className="text-lg font-medium">Select or create an agent</p>
                <p className="text-sm mt-1">Choose an agent from the sidebar to get started</p>
              </div>
            ) : activeTab === 'chat' ? (
              <ChatPanel
                agent={selectedAgent}
                history={history}
                loading={loading}
                onSend={handleSendMessage}
                onClearHistory={handleClearHistory}
              />
            ) : (
              <AgentDetail
                agent={selectedAgent}
                history={history}
                onEdit={() => { setEditingAgent(selectedAgent); setShowForm(true) }}
                onDelete={() => handleDeleteAgent(selectedAgent.id)}
              />
            )}
          </div>
        </div>

        {/* Right activity panel */}
        <div className="hidden lg:flex flex-col w-72 shrink-0 overflow-hidden" style={{ background: '#1a1d27' }}>
          <ActivityLog activity={activity} />
        </div>
      </div>

      {/* Agent form modal */}
      {showForm && (
        <AgentForm
          agent={editingAgent}
          onSave={handleSaveAgent}
          onCancel={() => { setShowForm(false); setEditingAgent(null) }}
        />
      )}
    </div>
  )
}
