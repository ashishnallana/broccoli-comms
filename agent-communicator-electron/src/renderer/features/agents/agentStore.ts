import type { AgentSummary } from '../../../shared/contracts'

export function groupAgents(agents: AgentSummary[]): Record<'groups' | 'agents', AgentSummary[]> {
  return {
    groups: agents.filter((agent) => agent.id.startsWith('group:')),
    agents: agents.filter((agent) => !agent.id.startsWith('group:')),
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
