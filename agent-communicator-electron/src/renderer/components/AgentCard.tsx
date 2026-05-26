import type { AgentSummary } from '../../shared/contracts'

interface Props {
  agent: AgentSummary
  selected: boolean
  onSelect: () => void
}

function initials(name: string): string {
  const parts = name.split(/[-_\s]+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

function statusDotClass(status: string): string {
  if (status === 'offline') return 'error'
  if (status === 'waiting' || status === 'busy') return 'warn'
  if (status === 'idle') return ''
  return 'idle'
}

export function avatarBg(name: string): string {
  const colors = [
    'var(--accent-blue)',
    'var(--accent-purple)',
    'var(--accent-pink)',
    'var(--accent-amber)',
    'var(--accent-emerald)',
    'var(--accent-teal)',
  ]
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  const index = Math.abs(hash) % colors.length
  return colors[index]
}

export function AgentCard({ agent, selected, onSelect }: Props) {
  return (
    <button className={`channel ${selected ? 'active' : ''}`} aria-pressed={selected} onClick={onSelect}>
      <span className="agent-avatar-sm" style={{ background: avatarBg(agent.displayName) }}>
        {initials(agent.displayName)}
      </span>
      <span className="channel-name">{agent.displayName}</span>
      <span className="channel-meta">
        <span className={`channel-status-dot ${statusDotClass(agent.status)}`} />
        {agent.unread > 0 && <span className="channel-badge">{agent.unread}</span>}
      </span>
    </button>
  )
}
