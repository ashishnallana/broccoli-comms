import type { AgentSummary } from '../../../shared/contracts'

export function groupAgents(
  agents: AgentSummary[],
  disabledAgentIds: ReadonlySet<string> = new Set(),
): Record<'mailbox' | 'groups' | 'agents' | 'disabled', AgentSummary[]> {
  const isMailbox = (agent: AgentSummary) => agent.id.startsWith('mailbox:')
  const isGroup = (agent: AgentSummary) => agent.id.startsWith('group:') || agent.id.startsWith('host:')
  const isDisabled = (agent: AgentSummary) => disabledAgentIds.has(agent.id)
  const isRegularAgent = (agent: AgentSummary) => !isMailbox(agent) && !isGroup(agent)

  return {
    mailbox: agents.filter(isMailbox),
    groups: agents.filter(isGroup),
    agents: agents.filter((agent) => isRegularAgent(agent) && !isDisabled(agent)),
    disabled: agents.filter((agent) => isRegularAgent(agent) && isDisabled(agent)),
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
