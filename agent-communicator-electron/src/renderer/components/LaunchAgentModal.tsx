import { useEffect, useState } from 'react'
import type { SavedAgent } from '../../shared/contracts'

interface Props {
  open: boolean
  savedAgents: SavedAgent[]
  onClose: () => void
  onLaunch: (configName: string, directory: string) => Promise<{ ok: boolean; error?: string }>
  onBrowseDirectory: () => Promise<string | null>
}

export function LaunchAgentModal({ open, savedAgents, onClose, onLaunch, onBrowseDirectory }: Props) {
  const [selectedConfig, setSelectedConfig] = useState('')
  const [selectedDir, setSelectedDir] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) {
      setError('')
      setLoading(false)
      if (savedAgents.length > 0) {
        const first = savedAgents[0]
        setSelectedConfig(first.name)
        setSelectedDir(first.directory || '')
      } else {
        setSelectedConfig('')
        setSelectedDir('')
      }
    }
  }, [open, savedAgents])

  function handleConfigChange(name: string) {
    setSelectedConfig(name)
    const agent = savedAgents.find((a) => a.name === name)
    if (agent) {
      setSelectedDir(agent.directory || '')
    }
  }

  async function handleBrowse() {
    setError('')
    const path = await onBrowseDirectory()
    if (path) {
      setSelectedDir(path)
    }
  }

  async function handleLaunch() {
    if (!selectedConfig || !selectedDir) return
    setLoading(true)
    setError('')
    const result = await onLaunch(selectedConfig, selectedDir)
    setLoading(false)
    if (result.ok) {
      onClose()
    } else {
      setError(result.error ?? 'Failed to spin agent')
    }
  }

  if (!open) return null

  const activeAgent = savedAgents.find((a) => a.name === selectedConfig)

  return (
    <div
      className="palette-backdrop open"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget && !loading) onClose()
      }}
    >
      <div
        className="palette"
        style={{
          width: '460px',
          padding: '20px',
          background: 'var(--surface-card)',
          border: '1px solid var(--hairline-strong)',
          borderRadius: 'var(--r-lg)',
          boxShadow: '0 20px 60px rgba(0, 0, 0, 0.6)',
        }}
      >
        <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '12px', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--on-dark)' }}>Launch Saved Agent</h3>
          <p style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>
            Select a template from your agent-tracker config to spin in a new Tmux session.
          </p>
        </div>

        {error && (
          <div
            style={{
              background: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              borderRadius: 'var(--r-md)',
              color: 'var(--accent-rose)',
              fontSize: '12px',
              padding: '10px 12px',
              marginBottom: '16px',
              lineHeight: '1.45',
            }}
          >
            {error}
          </div>
        )}

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '6px' }}>
            Agent Template
          </label>
          {savedAgents.length === 0 ? (
            <div className="empty-card" style={{ margin: 0, padding: '12px', fontSize: '12px' }}>
              No custom configurations found inside <code>~/.config/agent-tracker/agents/</code>
            </div>
          ) : (
            <>
              <select
                value={selectedConfig}
                onChange={(e) => handleConfigChange(e.target.value)}
                disabled={loading}
                style={{
                  width: '100%',
                  height: '36px',
                  background: 'var(--surface-elevated)',
                  border: '1px solid var(--hairline)',
                  borderRadius: 'var(--r-md)',
                  color: 'var(--on-dark)',
                  padding: '0 10px',
                  fontSize: '13px',
                  outline: 'none',
                }}
              >
                {savedAgents.map((agent) => (
                  <option key={agent.name} value={agent.name} style={{ background: 'var(--surface-card)' }}>
                    {agent.name}
                  </option>
                ))}
              </select>
              {activeAgent?.description && (
                <div style={{ fontSize: '11.5px', color: 'var(--muted)', marginTop: '6px', fontStyle: 'italic' }}>
                  {activeAgent.description}
                </div>
              )}
            </>
          )}
        </div>

        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '6px' }}>
            Working Directory (CWD)
          </label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              className="composer-input"
              value={selectedDir}
              placeholder="Pick a workspace directory..."
              onChange={(e) => setSelectedDir(e.target.value)}
              disabled={loading}
              style={{
                flex: 1,
                height: '36px',
                padding: '0 12px',
                background: 'var(--surface-elevated)',
                border: '1px solid var(--hairline)',
                borderRadius: 'var(--r-md)',
                color: 'var(--on-dark)',
                fontSize: '13px',
                outline: 'none',
              }}
            />
            <button
              className="btn"
              onClick={handleBrowse}
              disabled={loading}
              style={{
                height: '36px',
                background: 'var(--surface-soft)',
                borderColor: 'var(--hairline-strong)',
              }}
            >
              Browse...
            </button>
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '8px',
            borderTop: '1px solid var(--hairline)',
            paddingTop: '14px',
          }}
        >
          <button className="btn" onClick={onClose} disabled={loading} style={{ height: '32px', fontSize: '12px' }}>
            Cancel
          </button>
          <button
            className="btn primary"
            onClick={handleLaunch}
            disabled={loading || savedAgents.length === 0 || !selectedConfig || !selectedDir.trim()}
            style={{ height: '32px', fontSize: '12px', minWidth: '80px' }}
          >
            {loading ? 'Spinning...' : 'Launch'}
          </button>
        </div>
      </div>
    </div>
  )
}
