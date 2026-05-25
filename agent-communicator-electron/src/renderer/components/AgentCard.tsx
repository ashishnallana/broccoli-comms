import type { AgentSummary } from '../../shared/contracts'
import { statusGlyph } from '../lib/format'
import { relativeTime } from '../lib/time'

interface Props {
  agent: AgentSummary
  selected: boolean
  onSelect: () => void
}

export function AgentCard({ agent, selected, onSelect }: Props) {
  return (
    <button className={`agent-card ${agent.status} ${selected ? 'selected' : ''}`} aria-pressed={selected} onClick={onSelect}>
      <div className={`avatar ${agent.scope}`}>{agent.displayName.slice(0, 1).toUpperCase()}</div>
      <div className="agent-main">
        <div className="agent-title">
          <strong>{agent.displayName}</strong>
          <span className={`scope-pill ${agent.scope}`}>{agent.scope}</span>
        </div>
        <div className="agent-meta">
          <span className={`status-badge ${agent.status}`}>
            <span className={`status-dot ${agent.status}`}>{statusGlyph(agent.status)}</span>
            {agent.status}
          </span>
          <span>{agent.project}</span>
          <span>{relativeTime(agent.lastActiveAt)}</span>
        </div>
        <div className="agent-cwd">{agent.cwd}</div>
        <div className="agent-address">{agent.address}</div>
      </div>
      <div className="agent-card-side">
        {agent.unread > 0 ? <span className="unread">{agent.unread}</span> : <span className="read-indicator">read</span>}
        <span className={`direct-pill ${agent.canDirectControl ? 'enabled' : 'locked'}`}>
          {agent.canDirectControl ? 'direct' : 'locked'}
        </span>
      </div>
    </button>
  )
}
