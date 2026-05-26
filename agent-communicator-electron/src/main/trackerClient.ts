import { connect } from 'node:net'
import { basename, join } from 'node:path'
import { readdir, readFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import type { ActionResult, AgentStatus, AgentSummary, Message, RuntimeStatus, SavedAgent, SendResult, TargetRef } from '../shared/contracts'

interface RpcResponse<T> {
  result?: T
  error?: { code: number; message: string }
}

interface MailboxIdentity {
  name: string
  agent_id?: string
  uuid?: string
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
  // Do not inherit AGENT_NAME from the launching coding-agent pane: the
  // Electron app is a UI for the shared communicator identity, not the pane
  // that happened to start it.
  return env.BROCCOLI_COMMS_ELECTRON_AGENT_NAME || env.AGENT_COMMUNICATOR_ELECTRON_AGENT_NAME || DEFAULT_ELECTRON_SELF_AGENT
}

export function hasExplicitTrackerRuntime(env: NodeJS.ProcessEnv = process.env): boolean {
  return Boolean(resolveTrackerSocket(env))
}

export function localConversationKey(agent: Pick<TrackerAgent, 'agent_id' | 'uuid' | 'name'>, fallbackName: string): string {
  const stableID = agent.agent_id || agent.uuid
  return stableID ? `local:${stableID}` : fallbackName
}

export function trackerMessageTargetParams(target: TargetRef): Record<string, string> {
  if (target.scope === 'remote') {
    return { target_address: target.address }
  }
  if (target.address.includes('/') || target.address.startsWith('registry:')) {
    return { target_address: target.address }
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
  const isRemote = agent.scope === 'remote'
  const displayName = agent.name || name
  const conversationKey = isRemote ? `remote:${agent.target_address || name}` : localConversationKey(agent, displayName)
  const cwd = agent.cwd || ''
  return {
    id: conversationKey,
    name: displayName,
    displayName,
    scope: isRemote ? 'remote' : 'local',
    status: normalizeStatus(agent),
    cwd,
    project: isRemote ? agent.tracker_id || 'remote tracker' : projectFromCwd(cwd),
    address: agent.target_address || displayName,
    unread: 0,
    lastActiveAt: new Date().toISOString(),
    conversationKey,
    canDirectControl: false,
    tags: isRemote ? ['remote', 'registry'] : ['tracker', 'local', 'simple-view'],
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

export function spinSessionName(directory: string): string {
  const leaf = basename(directory).replace(/[^A-Za-z0-9_.-]/g, '_')
  return `${leaf}-spin`
}

function resolveAgentWrapperPath(): string {
  return process.env.BROCCOLI_COMMS_AGENT_WRAPPER || 'agent-wrapper'
}

function buildSpinCommand(agentCommand: string, agentArgs: string[]): string {
  const wrapper = resolveAgentWrapperPath()
  const innerCommand = `${wrapper} ${agentCommand} ${agentArgs.join(' ')}`
  const callerPath = process.env.PATH || ''
  return `bash -c 'export PATH="${callerPath}"; ${innerCommand}; zsh'`
}

export class LocalTrackerClient {
  private readonly sentMessagesByConversation = new Map<string, Message[]>()
  private readonly agentsByConversation = new Map<string, TrackerAgent>()
  private mailboxReady = false

  constructor(
    private readonly socketPath: string,
    private readonly selfAgentName = resolveSelfAgentName(),
  ) {}

  async getStatus(): Promise<RuntimeStatus> {
    let agents: Record<string, TrackerAgent> | undefined
    try {
      await this.ensureMailbox()
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
    await this.ensureMailbox()
    const agents = await this.call<Record<string, TrackerAgent>>('list', {
      agent_name: this.selfAgentName,
      include_remote: true,
    })
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
      await this.ensureMailbox()
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

  async sendPaneCapture(source: string, target: string): Promise<ActionResult> {
    try {
      await this.ensureMailbox()
      const isRemote = source.includes('/')
      let snapshot: any

      if (isRemote) {
        // Remote pane captures are requested via publish_tracker_event
        const remoteHost = source.split('/', 1)[0]
        const targetAgent = this.agentsByConversation.get(source)
        const targetTrackerId = targetAgent?.tracker_id
        if (!targetTrackerId) throw new Error(`Tracker ID not found for remote source ${source}`)

        const requestPayload = {
          request_id: `electron-req-${Date.now()}`,
          source: source.split('/', 2)[1],
          target: `${this.selfAgentName}`,
          requester: this.selfAgentName,
          format: 'markdown',
          last: 25,
          include_ansi: false,
          note: 'Requested from Electron communicator',
        }
        await this.call('publish_tracker_event', {
          target_tracker_id: targetTrackerId,
          event_type: 'pane_capture_request',
          payload: requestPayload,
        })
        return { ok: true, summary: `Remote pane capture request sent to ${remoteHost}` }
      } else {
        // Local pane captures: invoke capture_pane directly
        snapshot = await this.call<any>('capture_pane', { agent_name: source, last_lines: 25, include_ansi: false })
        if (!snapshot) throw new Error('Failed to capture pane snapshot')

        const messageText = `### Pane Capture Snapshot from ${snapshot.agent_name || source}\n` +
          `- **Pane:** ${snapshot.tmux_pane || 'unknown'}\n` +
          `- **Session:** ${snapshot.session || 'unknown'}\n` +
          `- **Copy Mode:** ${snapshot.copy_mode ? 'Active' : 'Inactive'}\n` +
          `- **Captured At:** ${snapshot.captured_at}\n` +
          `\n\`\`\`\n${snapshot.content || ''}\n\`\`\`\n`

        const targetAgent = this.agentsByConversation.get(target)
        const targetParams = targetAgent
          ? targetAgent.agent_id
            ? { agent_id: targetAgent.agent_id }
            : { agent_name: targetAgent.name }
          : { agent_name: target }

        await this.call('send_message', {
          ...targetParams,
          sender_name: source,
          sender_id: snapshot.agent_id,
          message: messageText,
        })
        return { ok: true, summary: `Snapshot sent successfully to ${target}` }
      }
    } catch (error) {
      return { ok: false, summary: '', error: error instanceof Error ? error.message : String(error) }
    }
  }

  async listSavedAgents(): Promise<SavedAgent[]> {
    const home = homedir()
    const agentsDir = join(home, '.config', 'agent-tracker', 'agents')
    const list: SavedAgent[] = []
    try {
      const entries = await readdir(agentsDir, { withFileTypes: true })
      for (const entry of entries) {
        if (!entry.isDirectory()) continue
        const configPath = join(agentsDir, entry.name, 'config.json')
        try {
          const content = await readFile(configPath, 'utf8')
          const raw = JSON.parse(content)
          list.push({
            name: entry.name,
            directory: raw.directory,
            agentCommand: raw['agent-command'] || raw.agentCommand,
            agentArgs: raw['agent-args'] || raw.agentArgs || [],
            description: raw.description || '',
          })
        } catch {
          // Skip invalid json
        }
      }
    } catch {
      // Skip missing folder
    }
    return list.sort((a, b) => a.name.localeCompare(b.name))
  }

  async spinAgent(configName: string, directory: string): Promise<ActionResult> {
    try {
      await this.ensureMailbox()
      const home = homedir()
      const configPath = join(home, '.config', 'agent-tracker', 'agents', configName, 'config.json')
      const content = await readFile(configPath, 'utf8')
      const raw = JSON.parse(content)

      const agentCommand = raw['agent-command'] || raw.agentCommand
      const agentArgs = raw['agent-args'] || raw.agentArgs || []
      if (!agentCommand) throw new Error(`Config ${configName} lacks 'agent-command' parameter`)

      const absoluteDir = join(directory.startsWith('~') ? directory.replace('~', home) : directory)
      const session = spinSessionName(absoluteDir)
      const command = buildSpinCommand(agentCommand, agentArgs)

      const env = { ...process.env }
      delete env.TMUX
      delete env.TMUX_PANE
      delete env.AGENT_ID
      delete env.AGENT_NAME
      delete env.AGENT_UUID

      const resolvedName = await this.call<string>('spin_agent', {
        session,
        directory: absoluteDir,
        command,
        name: session,
        env,
      })
      return { ok: true, summary: `Agent spun successfully as: ${resolvedName} in session: ${session}` }
    } catch (error) {
      return { ok: false, summary: '', error: error instanceof Error ? error.message : String(error) }
    }
  }

  private async ensureMailbox(): Promise<MailboxIdentity> {
    if (this.mailboxReady) return { name: this.selfAgentName }
    try {
      const mailbox = await this.call<MailboxIdentity>('ensure_mailbox', { agent_name: this.selfAgentName })
      this.mailboxReady = true
      return mailbox
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      if (!message.includes('Method not found')) throw error
      
      // Fallback: call standard 'register' RPC to auto-register the communicator identity
      try {
        const mailboxId = '00000000-0000-5000-8000-000000000001'
        await this.call('register', {
          session: 'mailbox',
          tmux_pane: 'none',
          wrapper_pid: 9999,
          tmux_socket: 'none',
          name: this.selfAgentName,
          agent_type: 'agent-communicator-ui',
          agent_cmd: 'agent-communicator-electron',
          agent_id: mailboxId,
          uuid: mailboxId,
          no_notify_with_send_keys: true,
          no_registry: true,
          cwd: '/tmp',
        })
        this.mailboxReady = true
        return { name: this.selfAgentName, agent_id: mailboxId, uuid: mailboxId }
      } catch (regError) {
        // If even standard register fails, log and degrade gracefully
        this.mailboxReady = true
        return { name: this.selfAgentName }
      }
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

