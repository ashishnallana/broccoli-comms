import type { AgentSummary } from '../../shared/contracts'

interface Props {
  agent: AgentSummary
  selected: boolean
  onSelect: () => void
  onContextMenu?: (e: React.MouseEvent, agentId: string) => void
}

function initials(name: string): string {
  const parts = name.split(/[-_\s]+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

function statusDotClass(status: string): string {
  if (status === 'offline') return 'error'
  if (status === 'waiting' || status === 'busy') return 'warn'
  if (status === 'idle') return 'idle'
  return 'idle'
}

function agentDisplayParts(agent: AgentSummary): { primary: string; secondary?: string } {
  if (agent.id.startsWith('group:') || agent.id.startsWith('host:') || agent.id.startsWith('mailbox:')) {
    return { primary: agent.displayName, secondary: agent.address }
  }

  let hostCandidate = agent.address || agent.name || agent.displayName
  if (hostCandidate.startsWith('registry:')) {
    hostCandidate = hostCandidate.slice('registry:'.length)
  }
  if (hostCandidate.includes(':')) {
    hostCandidate = hostCandidate.slice(hostCandidate.indexOf(':') + 1)
  }

  const slashIndex = hostCandidate.indexOf('/')
  if (slashIndex !== -1) {
    const host = hostCandidate.slice(0, slashIndex)
    const agentName = hostCandidate.slice(slashIndex + 1) || agent.displayName
    return { primary: agentName, secondary: host }
  }

  const displayName = agent.displayName.includes('/') ? agent.displayName.split('/').pop() || agent.displayName : agent.displayName
  return { primary: displayName, secondary: agent.scope === 'local' ? 'local-host' : undefined }
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

export function AgentCard({ agent, selected, onSelect, onContextMenu }: Props) {
  const { primary, secondary } = agentDisplayParts(agent)

  return (
    <button
      className={`channel ${selected ? 'active' : ''} ${agent.unread > 0 ? 'unread' : ''}`}
      aria-pressed={selected}
      onClick={onSelect}
      onContextMenu={(e) => onContextMenu?.(e, agent.id)}
    >
      <span className="agent-avatar-sm" style={{ background: avatarBg(primary) }}>
        {initials(primary)}
      </span>
      <span className="channel-copy">
        <span className="channel-name">{primary}</span>
        {secondary && <span className="channel-host">{secondary}</span>}
      </span>
      <span className="channel-meta">
        <span className={`channel-status-dot ${statusDotClass(agent.status)}`} />
        {agent.unread > 0 && <span className="channel-unread-dot" title="Unread messages" />}
      </span>
    </button>
  )
}
