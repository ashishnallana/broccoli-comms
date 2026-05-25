import { connect } from 'node:net'
import { basename, join } from 'node:path'
import type { AgentStatus, AgentSummary, Message, RuntimeStatus, SendResult, TargetRef } from '../shared/contracts'

interface RpcResponse<T> {
  result?: T
  error?: { code: number; message: string }
}

interface TrackerAgent {
  name?: string
  agent_id?: string
  uuid?: string
  status?: string
  waiting_approval?: boolean
  cwd?: string
  scope?: string
  target_address?: string
  tracker_id?: string
}

interface TrackerMessage {
  sender?: string
  sender_agent_id?: string
  sender_tracker_id?: string
  timestamp?: string
  message?: string
  delivered?: boolean
  read?: boolean
  message_id?: string
}

interface ReadInboxResult {
  mode?: string
  messages?: TrackerMessage[]
}

const allowedStatuses = new Set<AgentStatus>(['idle', 'busy', 'waiting', 'offline'])
export const DEFAULT_ELECTRON_SELF_AGENT = 'agent-communicator'

export function resolveTrackerSocket(env: NodeJS.ProcessEnv = process.env): string | undefined {
  if (env.AGENT_TRACKER_SOCKET) return env.AGENT_TRACKER_SOCKET
  if (env.BROCCOLI_COMMS_RUNTIME_DIR) return join(env.BROCCOLI_COMMS_RUNTIME_DIR, 'agent-tracker.sock')
  return undefined
}

export function resolveSelfAgentName(env: NodeJS.ProcessEnv = process.env): string {
  return env.BROCCOLI_COMMS_ELECTRON_AGENT_NAME || env.AGENT_COMMUNICATOR_ELECTRON_AGENT_NAME || env.AGENT_NAME || DEFAULT_ELECTRON_SELF_AGENT
}

export function hasExplicitTrackerRuntime(env: NodeJS.ProcessEnv = process.env): boolean {
  return Boolean(resolveTrackerSocket(env))
}

export function localConversationKey(agent: Pick<TrackerAgent, 'agent_id' | 'uuid' | 'name'>, fallbackName: string): string {
  const stableID = agent.agent_id || agent.uuid
  return stableID ? `local:${stableID}` : fallbackName
}

export function trackerMessageTargetParams(target: TargetRef): Record<string, string> {
  if (target.scope !== 'local') {
    throw new Error('tracker Simple View supports local targets only')
  }
  if (target.address.includes('/') || target.address.startsWith('registry:')) {
    throw new Error('tracker Simple View rejects host-qualified or registry targets')
  }
  const stableID = target.id.startsWith('local:') ? target.id.slice('local:'.length) : ''
  if (stableID) return { agent_id: stableID }
  return { agent_name: target.address }
}

function normalizeStatus(agent: TrackerAgent): AgentStatus {
  if (agent.waiting_approval) return 'waiting'
  const status = (agent.status || 'idle').toLowerCase()
  if (allowedStatuses.has(status as AgentStatus)) return status as AgentStatus
  if (status === 'working' || status === 'spawning' || status === 'running') return 'busy'
  return 'idle'
}

function projectFromCwd(cwd: string): string {
  return cwd ? basename(cwd) : 'unknown project'
}

export function trackerAgentToSummary(name: string, agent: TrackerAgent): AgentSummary | undefined {
  if (agent.scope === 'remote' || agent.target_address?.includes('/')) return undefined
  const displayName = agent.name || name
  const conversationKey = localConversationKey(agent, displayName)
  const cwd = agent.cwd || ''
  return {
    id: conversationKey,
    name: displayName,
    displayName,
    scope: 'local',
    status: normalizeStatus(agent),
    cwd,
    project: projectFromCwd(cwd),
    address: displayName,
    unread: 0,
    lastActiveAt: new Date().toISOString(),
    conversationKey,
    canDirectControl: false,
    tags: ['tracker', 'local', 'simple-view'],
  }
}

export function trackerMessageToMessage(conversationKey: string, message: TrackerMessage, selfAgentName = DEFAULT_ELECTRON_SELF_AGENT): Message {
  const author = message.sender || 'agent'
  const outbound = author === selfAgentName || author === 'you'
  return {
    id: message.message_id || `${conversationKey}-${message.timestamp || Date.now()}-${author}`,
    conversationKey,
    direction: outbound ? 'outbound' : 'inbound',
    author: outbound ? 'you' : author,
    body: message.message || '',
    createdAt: message.timestamp || new Date().toISOString(),
    deliveryState: message.delivered || outbound ? 'delivered' : 'received',
  }
}

export function messageMatchesConversation(message: TrackerMessage, target: Pick<TrackerAgent, 'agent_id' | 'uuid' | 'name'>): boolean {
  const stableID = target.agent_id || target.uuid
  if (stableID && message.sender_agent_id === stableID) return true
  return Boolean(target.name && message.sender === target.name)
}

export function mergeConversationMessages(inbound: Message[], sent: Message[]): Message[] {
  return [...inbound, ...sent].sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id))
}

export class LocalTrackerClient {
  private readonly sentMessagesByConversation = new Map<string, Message[]>()
  private readonly agentsByConversation = new Map<string, TrackerAgent>()

  constructor(
    private readonly socketPath: string,
    private readonly selfAgentName = resolveSelfAgentName(),
  ) {}

  async getStatus(): Promise<RuntimeStatus> {
    let agents: Record<string, TrackerAgent> | undefined
    try {
      agents = await this.call<Record<string, TrackerAgent>>('list', { agent_name: this.selfAgentName }, 1500)
    } catch {
      agents = undefined
    }
    const up = Boolean(agents)
    const selfRegistered = Boolean(agents?.[this.selfAgentName])
    return {
      mode: 'tracker',
      label: up
        ? selfRegistered
          ? 'Local tracker connected'
          : 'Local tracker connected; reply inbox identity not registered'
        : 'Local tracker unavailable',
      health: up ? (selfRegistered ? 'healthy' : 'degraded') : 'offline',
      tracker: up ? 'healthy' : 'offline',
      registry: 'offline',
      tmux: 'offline',
      updatedAt: new Date().toISOString(),
      notes: [
        `Using explicit tracker socket: ${this.socketPath}`,
        `Electron inbox identity: ${this.selfAgentName}`,
        selfRegistered
          ? 'Replies addressed to this identity can be read from its tracker inbox.'
          : 'Set BROCCOLI_COMMS_ELECTRON_AGENT_NAME to a registered local agent name to receive replies in this app.',
        'Simple View only: local tracker agents and one-to-one inbox messaging.',
        'Registry, remote protocol, and inherited tmux state are not used.',
      ],
    }
  }

  async listAgents(): Promise<AgentSummary[]> {
    const agents = await this.call<Record<string, TrackerAgent>>('list', { agent_name: this.selfAgentName })
    this.agentsByConversation.clear()
    return Object.entries(agents)
      .map(([name, agent]) => ({ ...agent, name: agent.name || name }))
      .filter((agent) => agent.name !== this.selfAgentName)
      .map((agent) => {
        const summary = trackerAgentToSummary(agent.name || '', agent)
        if (summary) this.agentsByConversation.set(summary.conversationKey, agent)
        return summary
      })
      .filter((agent): agent is AgentSummary => Boolean(agent))
  }

  async listMessages(conversationKey: string): Promise<Message[]> {
    if (conversationKey.includes('/') || conversationKey.startsWith('registry:')) {
      throw new Error('tracker Simple View supports local conversations only')
    }
    if (!this.agentsByConversation.has(conversationKey)) {
      await this.listAgents()
    }
    const selectedAgent = this.agentsByConversation.get(conversationKey)
    const sent = this.sentMessagesByConversation.get(conversationKey) ?? []
    if (!selectedAgent) return sent

    try {
      const senderFilter = selectedAgent.agent_id || selectedAgent.uuid
        ? { sender_agent_id: selectedAgent.agent_id || selectedAgent.uuid }
        : { sender_name: selectedAgent.name }
      const result = await this.call<ReadInboxResult>('get_inbox', {
        agent_name: this.selfAgentName,
        clear: false,
        last_n: 100,
        mark_read: false,
        ...senderFilter,
      })
      const inbound = (result.messages || [])
        .filter((message) => messageMatchesConversation(message, selectedAgent))
        .map((message) => trackerMessageToMessage(conversationKey, message, this.selfAgentName))
      return mergeConversationMessages(inbound, sent)
    } catch (error) {
      return mergeConversationMessages(
        [
          {
            id: `tracker-inbox-error-${conversationKey}`,
            conversationKey,
            direction: 'system',
            author: 'system',
            body: `Unable to read Electron inbox '${this.selfAgentName}'. Set BROCCOLI_COMMS_ELECTRON_AGENT_NAME to a registered local agent name to receive replies. ${
              error instanceof Error ? error.message : String(error)
            }`,
            createdAt: new Date().toISOString(),
            deliveryState: 'failed',
          },
        ],
        sent,
      )
    }
  }

  async sendMessage(target: TargetRef, body: string): Promise<SendResult> {
    const conversationKey = target.id || target.address
    try {
      await this.call('send_message', { ...trackerMessageTargetParams(target), sender_name: this.selfAgentName, message: body })
      const message = {
        id: `tracker-out-${Date.now()}`,
        conversationKey,
        direction: 'outbound' as const,
        author: 'you',
        body,
        createdAt: new Date().toISOString(),
        deliveryState: 'delivered' as const,
      }
      this.sentMessagesByConversation.set(conversationKey, [...(this.sentMessagesByConversation.get(conversationKey) ?? []), message])
      return { ok: true, message }
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) }
    }
  }

  private async ping(): Promise<boolean> {
    try {
      await this.call('list', {}, 1500)
      return true
    } catch {
      return false
    }
  }

  private call<T = unknown>(method: string, params: unknown, timeoutMs = 5000): Promise<T> {
    return new Promise((resolve, reject) => {
      const socket = connect(this.socketPath)
      const chunks: Buffer[] = []
      const timer = setTimeout(() => {
        socket.destroy(new Error(`tracker rpc ${method} timed out`))
      }, timeoutMs)

      socket.on('connect', () => {
        socket.end(JSON.stringify({ jsonrpc: '2.0', method, params, id: 1 }))
      })
      socket.on('data', (chunk) => chunks.push(Buffer.from(chunk)))
      socket.on('error', (error) => {
        clearTimeout(timer)
        reject(error)
      })
      socket.on('end', () => {
        clearTimeout(timer)
        try {
          const response = JSON.parse(Buffer.concat(chunks).toString('utf8')) as RpcResponse<T>
          if (response.error) reject(new Error(`tracker rpc ${method} failed: ${response.error.message}`))
          else resolve(response.result as T)
        } catch (error) {
          reject(error)
        }
      })
    })
  }
}

