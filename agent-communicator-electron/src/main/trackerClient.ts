import { connect } from 'node:net'
import { basename, dirname, join } from 'node:path'
import { existsSync } from 'node:fs'
import { readdir, readFile } from 'node:fs/promises'
import { homedir, hostname } from 'node:os'
import type { ActionResult, AgentStatus, AgentSummary, Message, MessageDeliveryState, RuntimeHealth, RuntimeStatus, SavedAgent, SendResult, TargetRef, GroupWatchParams } from '../shared/contracts'

interface RpcResponse<T> {
  result?: T
  error?: { code: number; message: string }
}

interface MailboxIdentity {
  name: string
  agent_id?: string
  uuid?: string
}

interface TrackerInfo {
  hostname?: string
  tracker_id?: string
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
  registry_name?: string
  tmux_socket?: string
}

interface TrackerMessage {
  sender?: string
  sender_agent_id?: string
  sender_tracker_id?: string
  timestamp?: string
  message?: string
  delivered?: boolean
  notified?: boolean
  read?: boolean
  message_id?: string
  recipient?: string
}

interface ReadInboxResult {
  mode?: string
  messages?: TrackerMessage[]
}

const allowedStatuses = new Set<AgentStatus>(['idle', 'busy', 'waiting', 'offline'])
export const DEFAULT_ELECTRON_SELF_AGENT = 'agent-communicator'

interface RegistryStatusEntry {
  connected?: boolean
  last_success?: number
  tracker_id?: string
  hostname?: string
}

interface RegistryStatusFile extends RegistryStatusEntry {
  registries?: Record<string, RegistryStatusEntry>
}

export function resolveTrackerSocket(env: NodeJS.ProcessEnv = process.env): string | undefined {
  if (env.AGENT_TRACKER_SOCKET) return env.AGENT_TRACKER_SOCKET
  if (env.BROCCOLI_COMMS_RUNTIME_DIR) return join(env.BROCCOLI_COMMS_RUNTIME_DIR, 'agent-tracker.sock')
  const defaultHomeManagerSocket = join(env.XDG_CACHE_HOME || join(homedir(), '.cache'), 'agent-tracker', 'agent-tracker.sock')
  if (existsSync(defaultHomeManagerSocket)) return defaultHomeManagerSocket
  return undefined
}

export function resolveTmuxSocket(trackerSocket?: string, env: NodeJS.ProcessEnv = process.env): string | undefined {
  if (env.AGENT_TRACKER_TMUX_SOCKET) return env.AGENT_TRACKER_TMUX_SOCKET
  if (env.BROCCOLI_COMMS_TMUX_SOCKET) return env.BROCCOLI_COMMS_TMUX_SOCKET
  if (!trackerSocket) return undefined
  if (trackerSocket.includes('/broccoli-comms/')) {
    return join(dirname(trackerSocket), 'tmux.sock')
  }
  return undefined
}

function registryStatusEntries(status?: RegistryStatusFile): RegistryStatusEntry[] {
  if (!status) return []
  const entries = Object.values(status.registries || {})
  return entries.length > 0 ? entries : [status]
}

function registryEntryFresh(entry: RegistryStatusEntry, now: number, maxAge: number): boolean {
  return Boolean(entry.connected && typeof entry.last_success === 'number' && now - entry.last_success <= maxAge)
}

function registryHeartbeatMaxAge(env: NodeJS.ProcessEnv = process.env): number {
  const raw = Number.parseInt(env.AGENT_REGISTRY_HEARTBEAT_SECONDS || '30', 10)
  const heartbeatSeconds = Number.isFinite(raw) && raw > 0 ? raw : 30
  return Math.max(heartbeatSeconds * 2 + 5, 15)
}

function registryStatusLastSuccess(status?: RegistryStatusFile): number {
  return registryStatusEntries(status).reduce((latest, entry) => {
    return typeof entry.last_success === 'number' && entry.last_success > latest ? entry.last_success : latest
  }, 0)
}

function trackerInfoMatchesRegistryStatus(status: RegistryStatusFile, trackerInfo?: TrackerInfo): boolean {
  if (!trackerInfo?.tracker_id && !trackerInfo?.hostname) return true
  const entries = registryStatusEntries(status)
  if (trackerInfo.tracker_id && entries.some((entry) => entry.tracker_id === trackerInfo.tracker_id)) return true
  if (trackerInfo.hostname && entries.some((entry) => entry.hostname === trackerInfo.hostname)) return true
  return false
}

function registryHealthFromStatus(status?: RegistryStatusFile, env: NodeJS.ProcessEnv = process.env): RuntimeHealth {
  const entries = registryStatusEntries(status)
  if (entries.length === 0) return 'offline'
  const now = Date.now() / 1000
  const maxAge = registryHeartbeatMaxAge(env)
  const fresh = entries.filter((entry) => registryEntryFresh(entry, now, maxAge)).length
  if (fresh === 0) return 'offline'
  if (fresh === entries.length) return 'healthy'
  return 'degraded'
}

function resolveRegistryStatusPaths(trackerSocket: string, env: NodeJS.ProcessEnv = process.env): string[] {
  const cacheHome = env.XDG_CACHE_HOME || join(homedir(), '.cache')
  const candidates: string[] = []
  if (env.BROCCOLI_COMMS_CACHE_DIR) {
    candidates.push(join(env.BROCCOLI_COMMS_CACHE_DIR, 'agent-tracker', 'registry-status.json'))
  }
  const broccoliDefault = join(cacheHome, 'broccoli-comms', 'agent-tracker', 'registry-status.json')
  const legacyDefault = join(cacheHome, 'agent-tracker', 'registry-status.json')
  if (trackerSocket.includes('/broccoli-comms/')) {
    candidates.push(broccoliDefault, legacyDefault)
  } else {
    candidates.push(legacyDefault, broccoliDefault)
  }
  return [...new Set(candidates)]
}

async function resolveRegistryHealth(trackerSocket: string, trackerInfo?: TrackerInfo): Promise<RuntimeHealth> {
  let best: RegistryStatusFile | undefined
  let bestScore = Number.NEGATIVE_INFINITY
  for (const path of resolveRegistryStatusPaths(trackerSocket)) {
    try {
      const status = JSON.parse(await readFile(path, 'utf8')) as RegistryStatusFile
      const score = (trackerInfoMatchesRegistryStatus(status, trackerInfo) ? 1_000_000_000 : 0) + registryStatusLastSuccess(status)
      if (score > bestScore) {
        best = status
        bestScore = score
      }
    } catch {
      // Ignore missing/invalid status files.
    }
  }
  return registryHealthFromStatus(best)
}

async function socketReachable(socketPath: string, timeoutMs = 500): Promise<boolean> {
  return await new Promise((resolve) => {
    const socket = connect(socketPath)
    let settled = false
    const finish = (ok: boolean) => {
      if (settled) return
      settled = true
      socket.destroy()
      resolve(ok)
    }
    socket.once('connect', () => finish(true))
    socket.once('error', () => finish(false))
    socket.setTimeout(timeoutMs, () => finish(false))
  })
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

  let address = agent.target_address || displayName
  if (isRemote && agent.registry_name && !address.includes(':')) {
    address = `${agent.registry_name}:${address}`
  }

  const conversationKey = isRemote ? `remote:${address}` : localConversationKey(agent, displayName)
  const cwd = agent.cwd || ''
  return {
    id: conversationKey,
    name: displayName,
    displayName,
    scope: isRemote ? 'remote' : 'local',
    status: normalizeStatus(agent),
    cwd,
    project: isRemote ? agent.tracker_id || 'remote tracker' : projectFromCwd(cwd),
    address,
    unread: 0,
    lastActiveAt: new Date().toISOString(),
    conversationKey,
    canDirectControl: false,
    tags: isRemote ? ['remote', 'registry'] : ['tracker', 'local', 'simple-view'],
  }
}

export function trackerMessageToMessage(conversationKey: string, message: TrackerMessage, recipient: string, selfAgentName = DEFAULT_ELECTRON_SELF_AGENT): Message {
  const author = message.sender || 'agent'
  const outbound = author === selfAgentName || author === 'you'
  return {
    id: message.message_id || `${conversationKey}-${message.timestamp || Date.now()}-${author}`,
    conversationKey,
    direction: outbound ? 'outbound' : 'inbound',
    author: outbound ? 'you' : author,
    recipient,
    body: message.message || '',
    createdAt: message.timestamp || new Date().toISOString(),
    deliveryState: message.read ? 'read' : message.notified ? 'notified' : message.delivered || outbound ? 'delivered' : 'received',
  }
}

export function messageMatchesConversation(message: TrackerMessage, target: Pick<TrackerAgent, 'agent_id' | 'uuid' | 'name'>): boolean {
  const stableID = target.agent_id || target.uuid
  if (stableID && message.sender_agent_id === stableID) return true
  
  if (!target.name) return false
  if (message.sender === target.name) return true
  
  if (target.name.includes('/')) {
    const segments = target.name.split('/')
    const bareName = segments[segments.length - 1]
    if (message.sender === bareName) return true
  }
  return false
}

export function mergeConversationMessages(inbound: Message[], sent: Message[]): Message[] {
  const byId = new Map<string, Message>()
  for (const message of [...inbound, ...sent]) {
    const existing = byId.get(message.id)
    if (!existing) {
      byId.set(message.id, message)
      continue
    }
    byId.set(message.id, {
      ...existing,
      ...message,
      createdAt: existing.createdAt <= message.createdAt ? existing.createdAt : message.createdAt,
      deliveryState: advanceDeliveryState(existing.deliveryState, message.deliveryState),
    })
  }
  return Array.from(byId.values()).sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id))
}

function deliveryStateForTrackerEvent(type: string | undefined): MessageDeliveryState | undefined {
  if (type === 'message_read') return 'read'
  if (type === 'message_notified') return 'notified'
  if (type === 'message_delivered') return 'delivered'
  return undefined
}

function advanceDeliveryState(current: MessageDeliveryState, next: MessageDeliveryState): MessageDeliveryState {
  const rank: Record<MessageDeliveryState, number> = {
    failed: -1,
    received: 0,
    sending: 1,
    sent: 2,
    delivered: 3,
    notified: 4,
    read: 5,
  }
  return rank[next] > rank[current] ? next : current
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

function trackerDirectInputTargetParams(target: TargetRef): Record<string, string> {
  const isRemote = target.id.startsWith('remote:')
  const stableID = target.id.startsWith('local:') ? target.id.slice('local:'.length) : isRemote ? target.id.slice('remote:'.length) : ''
  if (isRemote) return { target_address: target.address }
  if (stableID) return { agent_id: stableID }
  return { agent_name: target.address }
}

export class LocalTrackerClient {
  private readonly sentMessagesByConversation = new Map<string, Message[]>()
  private readonly agentsByConversation = new Map<string, TrackerAgent>()
  private mailboxReady = false

  constructor(
    private readonly socketPath: string,
    public readonly selfAgentName = resolveSelfAgentName(),
  ) {}

  async getStatus(): Promise<RuntimeStatus> {
    let agents: Record<string, TrackerAgent> | undefined
    let trackerInfo: TrackerInfo | undefined
    try {
      await this.ensureMailbox()
      agents = await this.call<Record<string, TrackerAgent>>('list', { agent_name: this.selfAgentName }, 1500)
      try {
        trackerInfo = await this.call<TrackerInfo>('tracker_info', {}, 1500)
      } catch {
        trackerInfo = undefined
      }
    } catch {
      agents = undefined
    }
    const up = Boolean(agents)
    const selfRegistered = Boolean(agents?.[this.selfAgentName])
    const registeredTmuxSocket = Object.values(agents || {}).map((agent) => agent.tmux_socket).find((socket) => socket && socket !== 'none')
    const tmuxSocket = registeredTmuxSocket || resolveTmuxSocket(this.socketPath)
    const [tmuxUp, registryHealth] = await Promise.all([
      tmuxSocket ? socketReachable(tmuxSocket) : Promise.resolve(up),
      resolveRegistryHealth(this.socketPath, trackerInfo),
    ])

    return {
      mode: 'tracker',
      label: up
        ? selfRegistered
          ? 'Local tracker connected'
          : 'Local tracker connected; reply inbox identity not registered'
        : 'Local tracker unavailable',
      health: up ? (selfRegistered && tmuxUp ? 'healthy' : 'degraded') : 'offline',
      tracker: up ? 'healthy' : 'offline',
      registry: registryHealth,
      tmux: tmuxUp ? 'healthy' : 'offline',
      updatedAt: new Date().toISOString(),
      notes: [
        `Using explicit tracker socket: ${this.socketPath}`,
        tmuxSocket ? `Using tmux socket: ${tmuxSocket}` : 'No explicit tmux socket detected; using tracker-backed default tmux integration.',
        `Electron inbox identity: ${this.selfAgentName}`,
        selfRegistered
          ? 'Replies addressed to this identity can be read from its tracker inbox.'
          : 'Set BROCCOLI_COMMS_ELECTRON_AGENT_NAME to a registered local agent name to receive replies in this app.',
        registryHealth === 'healthy'
          ? 'Registry heartbeat is fresh for this tracker runtime.'
          : registryHealth === 'degraded'
            ? 'Some configured registries are connected, but at least one heartbeat is stale or offline.'
            : 'No fresh registry heartbeat found for this tracker runtime.',
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

  async listMessages(conversationKey: string, inboxOwnerName?: string): Promise<Message[]> {
    if (conversationKey.startsWith('mailbox:')) {
      const mailboxName = conversationKey.slice('mailbox:'.length)
      try {
        const result = await this.call<ReadInboxResult>('get_inbox', {
          agent_name: mailboxName,
          clear: false,
          last_n: 100,
          mark_read: false
        })
        return (result.messages || []).map((message) => {
          return trackerMessageToMessage(conversationKey, message, message.recipient || 'you', this.selfAgentName)
        })
      } catch (error) {
        return []
      }
    }

    if (!this.agentsByConversation.has(conversationKey)) {
      await this.listAgents()
    }
    const selectedAgent = this.agentsByConversation.get(conversationKey)
    const sent = this.sentMessagesByConversation.get(conversationKey) ?? []
    if (!selectedAgent) return sent

    let peerSentList: Message[] = []
    if (selectedAgent.scope === 'local') {
      try {
        const peerInbox = await this.call<ReadInboxResult>('get_inbox', {
          agent_name: selectedAgent.name,
          clear: false,
          last_n: 100,
          mark_read: false
        })
        peerSentList = (peerInbox.messages || [])
          .filter((message) => message.sender === this.selfAgentName)
          .map((message) => trackerMessageToMessage(conversationKey, message, selectedAgent.name || 'local-agent', this.selfAgentName))
      } catch (e) {
        // Ignore if peer inbox is missing
      }
    }

    const combinedSent = mergeConversationMessages(peerSentList, sent)

    try {
      const senderFilter = selectedAgent.agent_id || selectedAgent.uuid
        ? { sender_agent_id: selectedAgent.agent_id || selectedAgent.uuid }
        : { sender_name: selectedAgent.name }
        
      const inboxQueryParams = inboxOwnerName && selectedAgent.scope === 'local'
        ? { agent_name: inboxOwnerName, clear: false, last_n: 100, mark_read: false }
        : { agent_name: this.selfAgentName, clear: false, last_n: 100, mark_read: false, ...senderFilter }

      const result = await this.call<ReadInboxResult>('get_inbox', inboxQueryParams)
      const inbound = (result.messages || [])
        .filter((message) => {
          if (inboxOwnerName && selectedAgent.scope === 'local') return true
          return messageMatchesConversation(message, selectedAgent)
        })
        .map((message) => {
          const recipientName = inboxOwnerName && selectedAgent.scope === 'local' ? selectedAgent.name || 'local-agent' : message.recipient || 'you'
          return trackerMessageToMessage(conversationKey, message, recipientName, this.selfAgentName)
        })
      return mergeConversationMessages(inbound, combinedSent)
    } catch (error) {
      return mergeConversationMessages(
        [
          {
            id: `tracker-inbox-error-${conversationKey}`,
            conversationKey,
            direction: 'system',
            author: 'system',
            recipient: 'system',
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

  async listGroupMessages(groupId: string): Promise<Message[]> {
    try {
      const result = await this.call<ReadInboxResult>('get_group_timeline', {
        group_id: groupId,
        last_n: 200
      })
      return (result.messages || []).map((message) => {
        return trackerMessageToMessage(groupId, message, message.recipient || 'you', this.selfAgentName)
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      if (message.includes('Method not found')) {
        throw new Error('Method not found: get_group_timeline')
      }
      return []
    }
  }

  async updateWatchlist(watchlist: string[] | GroupWatchParams): Promise<void> {
    if (watchlist && 'mode' in watchlist && watchlist.mode === 'group') {
      await this.call('update_watchlist', {
        watch_id: 'electron-active-group',
        mode: 'group',
        group_id: watchlist.groupId,
        members: watchlist.members,
        lease_seconds: 120,
        include_body: true
      })
    }
  }

  async sendMessage(target: TargetRef, body: string): Promise<SendResult> {
    const conversationKey = target.id || target.address
    try {
      await this.ensureMailbox()
      const messageId = `tracker-out-${Date.now()}-${Math.random().toString(16).slice(2)}`
      await this.call('send_message', { ...trackerMessageTargetParams(target), sender_name: this.selfAgentName, message: body, message_id: messageId })
      const message = {
        id: messageId,
        conversationKey,
        direction: 'outbound' as const,
        author: 'you',
        recipient: target.address,
        body,
        createdAt: new Date().toISOString(),
        deliveryState: 'sent' as const,
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
      const isRemote = source.startsWith('remote:')
      const cleanSource = isRemote ? source.slice('remote:'.length) : source.startsWith('local:') ? source.slice('local:'.length) : source
      let snapshot: any

      if (isRemote) {
        // Remote pane captures are requested via publish_tracker_event
        const remoteHost = cleanSource.split('/', 1)[0]
        const targetAgent = this.agentsByConversation.get(source)
        const targetTrackerId = targetAgent?.tracker_id
        if (!targetTrackerId) throw new Error(`Tracker ID not found for remote source ${cleanSource}`)

        const localHost = await this.resolveTrackerHostname()
        const qualifiedTarget = `${localHost}/${this.selfAgentName}`

        const requestPayload = {
          request_id: `electron-req-${Date.now()}`,
          source: cleanSource.split('/', 2)[1],
          target: qualifiedTarget,
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
        const sourceAgent = this.agentsByConversation.get(source)
        const captureParams = sourceAgent
          ? sourceAgent.agent_id
            ? { agent_id: sourceAgent.agent_id }
            : { agent_name: sourceAgent.name }
          : { agent_name: cleanSource }

        snapshot = await this.call<any>('capture_pane', { ...captureParams, last_lines: 25, include_ansi: false })
        if (!snapshot) throw new Error('Failed to capture pane snapshot')

        const messageText = `### Pane Capture Snapshot from ${snapshot.agent_name || sourceAgent?.name || cleanSource}\n` +
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
          sender_name: sourceAgent?.name || cleanSource,
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
      const ready = await this.waitForRegisteredAgent(resolvedName)
      return {
        ok: true,
        summary: ready
          ? `Agent spun successfully as: ${resolvedName} in session: ${session}`
          : `Agent ${resolvedName} is starting in session: ${session}; it will become interactive once registration completes.`,
      }
    } catch (error) {
      return { ok: false, summary: '', error: error instanceof Error ? error.message : String(error) }
    }
  }

  private async waitForRegisteredAgent(agentName: string, timeoutMs = 10000): Promise<boolean> {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      try {
        const agents = await this.call<Record<string, TrackerAgent>>('list', { agent_name: this.selfAgentName }, 1500)
        const agent = agents[agentName]
        if (agent?.agent_id && agent.status !== 'spawning') return true
      } catch {
        // Keep polling until the startup deadline.
      }
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
    return false
  }

  async sendDirectText(target: TargetRef, text: string, submit: boolean): Promise<ActionResult> {
    try {
      await this.ensureMailbox()
      const params = {
        input_type: 'text',
        text,
        submit,
        sender_name: this.selfAgentName,
        ...trackerDirectInputTargetParams(target),
      }
      await this.call('send_input', params)
      return { ok: true, summary: `Direct text successfully injected` }
    } catch (error) {
      return { ok: false, summary: '', error: error instanceof Error ? error.message : String(error) }
    }
  }

  async sendDirectKeys(target: TargetRef, keys: string[]): Promise<ActionResult> {
    try {
      await this.ensureMailbox()
      const params = {
        input_type: 'keys',
        keys,
        sender_name: this.selfAgentName,
        ...trackerDirectInputTargetParams(target),
      }
      await this.call('send_input', params)
      return { ok: true, summary: `Direct keys successfully injected` }
    } catch (error) {
      return { ok: false, summary: '', error: error instanceof Error ? error.message : String(error) }
    }
  }

  async waitEvents(clientId: string, cursor: number, watchlist: string[], leaseSeconds: number): Promise<{ events: any[]; lastSeq: number; reset?: boolean; gap?: boolean }> {
    await this.ensureMailbox()
    const response = await this.call<{ events: any[]; last_seq: number; reset?: boolean; gap?: boolean }>('wait_events', {
      client_id: clientId,
      cursor,
      watch_list: watchlist,
      lease_seconds: leaseSeconds,
      timeout: 25
    })
    this.applyOutboundStatusEvents(response.events || [])
    return {
      events: response.events,
      lastSeq: response.last_seq,
      reset: response.reset,
      gap: response.gap
    }
  }

  private applyOutboundStatusEvents(events: any[]): void {
    for (const event of events) {
      const nextState = deliveryStateForTrackerEvent(event.event_type ?? event.type)
      const messageId = event.message_id ?? event.messageId ?? event.payload?.message_id
      if (!nextState || !messageId) continue
      for (const [conversationKey, sent] of this.sentMessagesByConversation.entries()) {
        let changed = false
        const updated = sent.map((message) => {
          if (message.id !== messageId) return message
          changed = true
          return { ...message, deliveryState: advanceDeliveryState(message.deliveryState, nextState) }
        })
        if (changed) this.sentMessagesByConversation.set(conversationKey, updated)
      }
    }
  }

  private async resolveTrackerHostname(): Promise<string> {
    try {
      const info = await this.call<TrackerInfo>('tracker_info', {}, 1500)
      if (info.hostname) return info.hostname
    } catch {
      // Older trackers did not expose tracker_info; fall back to environment/OS hostname.
    }
    return process.env.AGENT_TRACKER_HOSTNAME || hostname()
  }

  private async ensureMailbox(): Promise<MailboxIdentity> {
    if (this.mailboxReady) return { name: this.selfAgentName }
    try {
      const mailbox = await this.call<MailboxIdentity>('ensure_mailbox', { agent_name: this.selfAgentName, no_registry: false })
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
          no_registry: false,
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

