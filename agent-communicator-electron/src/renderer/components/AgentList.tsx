import { useMemo, useState } from 'react'
import type { AgentScope, AgentSummary } from '../../shared/contracts'
import { groupAgents } from '../features/agents/agentStore'
import { AgentCard } from './AgentCard'

interface Props {
  agents: AgentSummary[]
  selectedId?: string
  onSelect: (agent: AgentSummary) => void
}

const scopes: AgentScope[] = ['local', 'remote']

export function AgentList({ agents, selectedId, onSelect }: Props) {
  const [query, setQuery] = useState('')
  const normalizedQuery = query.trim().toLowerCase()
  const visibleAgents = useMemo(() => {
    if (!normalizedQuery) return agents
    return agents.filter((agent) =>
      [agent.displayName, agent.name, agent.cwd, agent.project, agent.address, agent.status, agent.scope]
        .join(' ')
        .toLowerCase()
        .includes(normalizedQuery),
    )
  }, [agents, normalizedQuery])
  const grouped = groupAgents(visibleAgents)
  const unreadTotal = agents.reduce((total, agent) => total + agent.unread, 0)

  return (
    <section className="agent-list-pane">
      <div className="pane-header">
        <div>
          <span className="eyebrow">Fixtures</span>
          <h2>Agents</h2>
        </div>
        <div className="pane-counts" aria-label="Agent counts">
          <span className="count-pill">{agents.length} total</span>
          <span className="count-pill accent">{unreadTotal} unread</span>
        </div>
      </div>
      <label className="agent-search">
        <span>Search mock agents</span>
        <input value={query} placeholder="Name, cwd, project, status…" onChange={(event) => setQuery(event.target.value)} />
      </label>
      {visibleAgents.length === 0 ? (
        <div className="list-empty">
          <strong>No fixture agents match.</strong>
          <span>Try clearing the search or matching a project, cwd, status, or scope label.</span>
        </div>
      ) : (
        scopes.map((scope) => (
          <div className="agent-group" key={scope}>
            <div className="group-label">
              <span>{scope} mock agents</span>
              <span>{grouped[scope].length}</span>
            </div>
            {grouped[scope].length === 0 ? (
              <div className="group-empty">No {scope} agents in this filtered fixture view.</div>
            ) : (
              grouped[scope].map((agent) => (
                <AgentCard key={agent.id} agent={agent} selected={agent.id === selectedId} onSelect={() => onSelect(agent)} />
              ))
            )}
          </div>
        ))
      )}
    </section>
  )
}
