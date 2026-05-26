import type { AgentSummary } from '../../../shared/contracts'

export function groupAgents(agents: AgentSummary[]): Record<'local' | 'remote', AgentSummary[]> {
  return {
    local: agents.filter((agent) => agent.scope === 'local'),
    remote: agents.filter((agent) => agent.scope === 'remote'),
  }
}

export function conversationKeyForAgent(agent: Pick<AgentSummary, 'address' | 'name'>): string {
  return agent.address || agent.name
}

export function targetForAgent(agent: AgentSummary) {
  return {
    scope: agent.scope,
    id: agent.id,
    address: conversationKeyForAgent(agent),
    host: agent.scope === 'remote' ? conversationKeyForAgent(agent).split('/')[0] : undefined,
  }
}
