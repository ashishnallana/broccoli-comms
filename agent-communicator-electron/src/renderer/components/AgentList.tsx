import { useEffect, useMemo, useState } from 'react'
import type { AgentScope, AgentSummary } from '../../shared/contracts'
import { groupAgents } from '../features/agents/agentStore'
import { AgentCard } from './AgentCard'

interface Props {
  agents: AgentSummary[]
  disabledAgentIds?: ReadonlySet<string>
  selectedId?: string
  onSelect: (agent: AgentSummary) => void
  onVisibleAgentsChange?: (agents: AgentSummary[], filterActive: boolean) => void
  onOpenLaunch: () => void
  onOpenCreateGroup?: () => void
  onAgentContextMenu?: (e: React.MouseEvent, agentId: string) => void
  onRefresh?: () => void
  refreshing?: boolean
}

const categories = ['mailbox', 'groups', 'agents', 'disabled'] as const

export function AgentList({ agents, disabledAgentIds = new Set(), selectedId, onSelect, onVisibleAgentsChange, onOpenLaunch, onOpenCreateGroup, onAgentContextMenu, onRefresh, refreshing = false }: Props) {
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
  const grouped = groupAgents(visibleAgents, disabledAgentIds)
  const unreadTotal = agents.reduce((total, agent) => total + agent.unread, 0)

  useEffect(() => {
    onVisibleAgentsChange?.(visibleAgents, filterActive)
  }, [filterActive, onVisibleAgentsChange, visibleAgents])

  return (
    <section className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-header-row">
          <div className="workspace">
            <div className="workspace-icon">A</div>
            <div>
              <div className="workspace-name">Agent Monitor</div>
              <div className="workspace-sub">
                {agents.length} agents · {unreadTotal} unread
              </div>
            </div>
          </div>
          {onRefresh && (
            <button
              type="button"
              className={`agent-refresh-button ${refreshing ? 'spinning' : ''}`}
              title="Refresh local and remote agents"
              aria-label="Refresh local and remote agents"
              onClick={onRefresh}
              disabled={refreshing}
            >
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M13 8a5 5 0 1 1-1.46-3.54" />
                <path d="M13 3.5v3h-3" />
              </svg>
            </button>
          )}
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
          categories.map((cat) => (
            <div className="agent-section" key={cat}>
              <div className="section-head">
                <span className="section-head-title" style={{ textTransform: 'capitalize' }}>{cat}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {cat === 'groups' && onOpenCreateGroup && (
                    <button
                      className="section-head-add"
                      title="Create custom group channel"
                      onClick={onOpenCreateGroup}
                      style={{ cursor: 'pointer' }}
                    >
                      +
                    </button>
                  )}
                  {cat === 'agents' && (
                    <button
                      className="section-head-add"
                      title="Launch saved agent configuration"
                      onClick={onOpenLaunch}
                      style={{ cursor: 'pointer' }}
                    >
                      +
                    </button>
                  )}
                  <span className="section-head-count">{grouped[cat].length}</span>
                </div>
              </div>
              {grouped[cat].length === 0 ? (
                <div className="empty-card">No {cat} match filters.</div>
              ) : (
                grouped[cat].map((agent) => (
                  <AgentCard key={agent.id} agent={agent} selected={agent.id === selectedId} onSelect={() => onSelect(agent)} onContextMenu={onAgentContextMenu} />
                ))
              )}
            </div>
          ))
        )}
      </div>

      <div className="agents-col-footer">
        <div className="footer-label">Safety boundary</div>
        <div className="footer-body">Registry-aware inbox messaging. Ctrl-N / Ctrl-P follows the filtered list and skips disabled agents.</div>
      </div>
    </section>
  )
}
