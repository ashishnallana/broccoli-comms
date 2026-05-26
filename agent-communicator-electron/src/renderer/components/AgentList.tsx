import { useEffect, useMemo, useState } from 'react'
import type { AgentScope, AgentSummary } from '../../shared/contracts'
import { groupAgents } from '../features/agents/agentStore'
import { AgentCard } from './AgentCard'

interface Props {
  agents: AgentSummary[]
  selectedId?: string
  onSelect: (agent: AgentSummary) => void
  onVisibleAgentsChange?: (agents: AgentSummary[], filterActive: boolean) => void
  onOpenLaunch: () => void
  onAgentContextMenu?: (e: React.MouseEvent, agentId: string) => void
}

const scopes: AgentScope[] = ['local', 'remote']

export function AgentList({ agents, selectedId, onSelect, onVisibleAgentsChange, onOpenLaunch, onAgentContextMenu }: Props) {
  const [query, setQuery] = useState('')
  const normalizedQuery = query.trim().toLowerCase()
  const filterActive = normalizedQuery.length > 0
  const visibleAgents = useMemo(() => {
    if (!filterActive) return agents
    return agents.filter((agent) =>
      [agent.displayName, agent.name, agent.cwd, agent.project, agent.address, agent.status, agent.scope]
        .join(' ')
        .toLowerCase()
        .includes(normalizedQuery),
    )
  }, [agents, filterActive, normalizedQuery])
  const grouped = groupAgents(visibleAgents)
  const unreadTotal = agents.reduce((total, agent) => total + agent.unread, 0)

  useEffect(() => {
    onVisibleAgentsChange?.(visibleAgents, filterActive)
  }, [filterActive, onVisibleAgentsChange, visibleAgents])

  return (
    <section className="sidebar">
      <div className="sidebar-header">
        <div className="workspace">
          <div className="workspace-icon">A</div>
          <div>
            <div className="workspace-name">Agent Monitor</div>
            <div className="workspace-sub">
              {agents.length} agents · {unreadTotal} unread
            </div>
          </div>
        </div>
      </div>

      <div className="subnav" role="tablist" aria-label="Communicator sections">
        <button className="subnav-item active">Agents</button>
      </div>

      <input
        className="search-input"
        value={query}
        placeholder="Search agents, cwd, project…"
        onChange={(event) => setQuery(event.target.value)}
      />

      <div className="sidebar-scroll">
        <div className="locked-banner">
          <svg className="locked-banner-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <rect x="3" y="7" width="10" height="7" rx="1.5" />
            <path d="M5.5 7V4.5a2.5 2.5 0 015 0V7" />
          </svg>
          <div>
            <span className="locked-banner-title">Direct controls locked</span>
            Normal inbox messages use the shared agent-communicator identity.
          </div>
        </div>

        {visibleAgents.length === 0 ? (
          <div className="empty-card">No agents match this filtered view.</div>
        ) : (
          scopes.map((scope) => (
            <div className="agent-section" key={scope}>
              <div className="section-head">
                <span className="section-head-title">{scope} Agents</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {scope === 'local' && (
                    <button
                      className="section-head-add"
                      title="Launch saved agent configuration"
                      onClick={onOpenLaunch}
                      style={{ cursor: 'pointer' }}
                    >
                      +
                    </button>
                  )}
                  <span className="section-head-count">{grouped[scope].length}</span>
                </div>
              </div>
              {grouped[scope].length === 0 ? (
                <div className="empty-card">No {scope} agents match filters.</div>
              ) : (
                grouped[scope].map((agent) => (
                  <AgentCard key={agent.id} agent={agent} selected={agent.id === selectedId} onSelect={() => onSelect(agent)} onContextMenu={onAgentContextMenu} />
                ))
              )}
            </div>
          ))
        )}
      </div>

      <div className="agents-col-footer">
        <div className="footer-label">Safety boundary</div>
        <div className="footer-body">Local tracker messaging only. Ctrl-N / Ctrl-P follows the filtered agent list.</div>
      </div>
    </section>
  )
}
