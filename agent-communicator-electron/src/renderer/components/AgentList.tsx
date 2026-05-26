import { useEffect, useMemo, useState } from 'react'
import type { AgentScope, AgentSummary } from '../../shared/contracts'
import { groupAgents } from '../features/agents/agentStore'
import { AgentCard } from './AgentCard'

interface Props {
  agents: AgentSummary[]
  selectedId?: string
  onSelect: (agent: AgentSummary) => void
  onVisibleAgentsChange?: (agents: AgentSummary[], filterActive: boolean) => void
}

const scopes: AgentScope[] = ['local', 'remote']

export function AgentList({ agents, selectedId, onSelect, onVisibleAgentsChange }: Props) {
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
    <section className="agents-col">
      <div className="col-header">
        <div className="brand">
          <div className="brand-logo">A</div>
          <div>
            <div className="brand-name">Agent Communicator</div>
            <div className="brand-sub">Electron app · shared inbox</div>
          </div>
        </div>

        <div className="subnav" role="tablist" aria-label="Communicator sections">
          <button className="subnav-item active">Agents</button>
          <button className="subnav-item">Prompts</button>
          <button className="subnav-item">Settings</button>
        </div>
      </div>

      <div className="agents-head">
        <div className="agents-head-row">
          <h2>Agents</h2>
          <div className="count-cluster" aria-label="Agent counts">
            <span className="count-pill">
              <strong>{agents.length}</strong> total
            </span>
            <span className="count-pill">
              <strong>{unreadTotal}</strong> unread
            </span>
          </div>
        </div>
        <input
          className="search-input"
          value={query}
          placeholder="Search agents, cwd, project…"
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      <div className="agents-list">
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
              <div className="section-label">
                <span className="section-label-text">{scope}</span>
                <span className="section-count">{grouped[scope].length}</span>
              </div>
              {grouped[scope].length === 0 ? (
                <div className="empty-card">No {scope} agents in this filtered view.</div>
              ) : (
                grouped[scope].map((agent) => (
                  <AgentCard key={agent.id} agent={agent} selected={agent.id === selectedId} onSelect={() => onSelect(agent)} />
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
