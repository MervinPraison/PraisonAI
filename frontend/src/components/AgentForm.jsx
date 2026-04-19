import { useState, useEffect } from 'react'

const LLM_MODELS = [
  'gpt-4o-mini',
  'gpt-4o',
  'claude-3-haiku',
  'claude-3-5-sonnet',
  'gemini-1.5-flash',
]

const STATUSES = ['active', 'auditing', 'decommissioned']

const defaultForm = (agent) => ({
  name: agent?.name || '',
  instructions: agent?.instructions || '',
  model: agent?.model || agent?.llm || 'gpt-4o-mini',
  status: agent?.status || 'active',
})

export default function AgentForm({ agent, onSave, onCancel }) {
  const [form, setForm] = useState(() => defaultForm(agent))

  // Re-sync if the parent passes a different agent (e.g. switching edit targets).
  useEffect(() => { setForm(defaultForm(agent)) }, [agent?.id])

  // Dismiss on Escape key.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  const set = (key, val) => setForm(prev => ({ ...prev, [key]: val }))

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!form.name.trim()) return
    onSave(form)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="agent-form-title"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
      onClick={e => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl" style={{ background: '#1a1d27', border: '1px solid #2a2d3e' }}>
        <form onSubmit={handleSubmit}>
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: '#2a2d3e' }}>
            <h2 id="agent-form-title" className="text-lg font-bold text-white">{agent ? 'Edit Agent' : 'New Agent'}</h2>
            <button type="button" onClick={onCancel} aria-label="Close agent form" className="p-1.5 rounded-lg hover:bg-white/10 transition-colors text-gray-400">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="px-6 py-5 space-y-5">
            {/* Name */}
            <Field label="Name *">
              <input
                type="text"
                value={form.name}
                onChange={e => set('name', e.target.value)}
                placeholder="Research Agent"
                required
                className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
                style={{ background: '#0f1117', border: '1px solid #2a2d3e', color: '#e2e8f0' }}
                onFocus={e => e.target.style.borderColor = '#6c63ff'}
                onBlur={e => e.target.style.borderColor = '#2a2d3e'}
              />
            </Field>

            {/* Instructions */}
            <Field label="Instructions / System Prompt">
              <textarea
                value={form.instructions}
                onChange={e => set('instructions', e.target.value)}
                placeholder="You are a helpful assistant that..."
                rows={4}
                className="w-full px-3 py-2.5 rounded-lg text-sm outline-none resize-none"
                style={{ background: '#0f1117', border: '1px solid #2a2d3e', color: '#e2e8f0' }}
                onFocus={e => e.target.style.borderColor = '#6c63ff'}
                onBlur={e => e.target.style.borderColor = '#2a2d3e'}
              />
            </Field>

            {/* Model + Status */}
            <div className="grid grid-cols-2 gap-4">
              <Field label="Model">
                <input
                  type="text"
                  list="llm-models"
                  value={form.model}
                  onChange={e => set('model', e.target.value)}
                  placeholder="gpt-4o-mini"
                  className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
                  style={{ background: '#0f1117', border: '1px solid #2a2d3e', color: '#e2e8f0' }}
                  onFocus={e => e.target.style.borderColor = '#6c63ff'}
                  onBlur={e => e.target.style.borderColor = '#2a2d3e'}
                />
                <datalist id="llm-models">
                  {/* Prepend current value if it's not already in the list */}
                  {!LLM_MODELS.includes(form.model) && form.model && (
                    <option value={form.model} />
                  )}
                  {LLM_MODELS.map(m => <option key={m} value={m} />)}
                </datalist>
              </Field>
              <Field label="Status">
                <div className="flex flex-wrap gap-3 pt-1">
                  {STATUSES.map(s => (
                    <label key={s} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="status"
                        value={s}
                        checked={form.status === s}
                        onChange={() => set('status', s)}
                        className="sr-only"
                      />
                      <div
                        aria-hidden="true"
                        className="w-4 h-4 rounded-full border-2 flex items-center justify-center transition-colors"
                        style={{ borderColor: form.status === s ? '#6c63ff' : '#4b5563', background: form.status === s ? '#6c63ff' : 'transparent' }}
                      >
                        {form.status === s && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                      </div>
                      <span className="text-sm" style={{ color: '#d1d5db' }}>{s}</span>
                    </label>
                  ))}
                </div>
              </Field>
            </div>
          </div>

          {/* Footer */}
          <div className="flex gap-3 justify-end px-6 py-4 border-t" style={{ borderColor: '#2a2d3e' }}>
            <button
              type="button"
              onClick={onCancel}
              className="px-5 py-2.5 rounded-xl text-sm font-medium transition-colors hover:bg-white/5"
              style={{ border: '1px solid #2a2d3e', color: '#9ca3af' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-5 py-2.5 rounded-xl text-sm font-medium transition-all hover:opacity-90 active:scale-95"
              style={{ background: '#6c63ff', color: 'white' }}
            >
              {agent ? 'Save Changes' : 'Create Agent'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: '#6b7280' }}>
        {label}
      </label>
      {children}
    </div>
  )
}
