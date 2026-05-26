import type { AgentSummary } from '../../shared/contracts'
import { relativeTime } from '../lib/time'

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

function stateClass(agent: AgentSummary): string {
  if (agent.unread > 0) return 'has-unread'
  if (agent.status === 'offline') return 'has-status status-error'
  if (agent.status === 'waiting' || agent.status === 'busy') return 'has-status status-warn'
  if (agent.status === 'idle') return 'has-status'
  return ''
}

export function AgentCard({ agent, selected, onSelect }: Props) {
  return (
    <button className={`agent-card ${selected ? 'active' : ''} ${stateClass(agent)}`} aria-pressed={selected} onClick={onSelect}>
      <div className="agent-avatar">{initials(agent.displayName)}</div>
      <div className="agent-main">
        <div className="agent-name-row">
          <span className="agent-name">{agent.displayName}</span>
          <span className="agent-time">{relativeTime(agent.lastActiveAt).replace(' ago', '')}</span>
        </div>
        <div className="agent-project">
          <span className="proj-host">{agent.project || agent.scope}</span> · {agent.cwd || agent.address}
        </div>
      </div>
    </button>
  )
}
