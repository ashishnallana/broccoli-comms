export type AgentScope = 'local' | 'remote'
export type AgentStatus = 'idle' | 'busy' | 'waiting' | 'offline'
export type RuntimeHealth = 'healthy' | 'degraded' | 'offline'
export type ComposerMode = 'message' | 'directText' | 'directKeys'

export interface RuntimeStatus {
  mode: 'mock'
  label: string
  health: RuntimeHealth
  tracker: RuntimeHealth
  registry: RuntimeHealth
  tmux: RuntimeHealth
  updatedAt: string
  notes: string[]
}

export interface TargetRef {
  scope: AgentScope
  id: string
  address: string
  host?: string
}

export interface AgentSummary {
  id: string
  name: string
  displayName: string
  scope: AgentScope
  status: AgentStatus
  cwd: string
  project: string
  address: string
  unread: number
  lastActiveAt: string
  conversationKey: string
  canDirectControl: boolean
  tags: string[]
}

export type MessageDirection = 'inbound' | 'outbound' | 'system'
export type MessageDeliveryState = 'received' | 'sending' | 'delivered' | 'failed'

export interface Message {
  id: string
  conversationKey: string
  direction: MessageDirection
  author: string
  body: string
  createdAt: string
  deliveryState: MessageDeliveryState
}

export interface SendResult {
  ok: boolean
  message?: Message
  error?: string
}

export interface ActionResult {
  ok: boolean
  summary: string
  error?: string
}

export interface CommunicatorRuntimeClient {
  getStatus(): Promise<RuntimeStatus>
  listAgents(): Promise<AgentSummary[]>
  listMessages(conversationKey: string): Promise<Message[]>
  sendMessage(target: TargetRef, body: string): Promise<SendResult>
  sendDirectText(target: TargetRef, text: string, submit: boolean): Promise<ActionResult>
  sendDirectKeys(target: TargetRef, keys: string[]): Promise<ActionResult>
}
