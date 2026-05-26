import type { ActionResult, AgentSummary, Message, RuntimeStatus, SavedAgent, SendResult, TargetRef } from '../../../shared/contracts'
import { mockAgents, mockMessages, mockRuntimeStatus } from '../../../test/fixtures'
import { nextMockId } from '../../lib/ids'

const latency = (ms = 120) => new Promise((resolve) => setTimeout(resolve, ms))
const clone = <T>(value: T): T => structuredClone(value)

export class MockRuntimeClient {
  private status: RuntimeStatus = clone(mockRuntimeStatus)
  private agents: AgentSummary[] = clone(mockAgents)
  private messages: Record<string, Message[]> = clone(mockMessages)

  async getStatus(): Promise<RuntimeStatus> {
    await latency()
    return clone(this.status)
  }

  async listAgents(): Promise<AgentSummary[]> {
    await latency()
    return clone(this.agents)
  }

  async listMessages(conversationKey: string): Promise<Message[]> {
    await latency()
    return clone(this.messages[conversationKey] ?? [])
  }

  async sendMessage(target: TargetRef, body: string): Promise<SendResult> {
    await latency(180)
    const message: Message = {
      id: nextMockId('msg'),
      conversationKey: target.address,
      direction: 'outbound',
      author: 'you',
      body,
      createdAt: new Date().toISOString(),
      deliveryState: 'delivered',
    }
    this.messages[message.conversationKey] = [...(this.messages[message.conversationKey] ?? []), message]
    return { ok: true, message: clone(message) }
  }

  async sendDirectText(target: TargetRef, _text: string, submit: boolean): Promise<ActionResult> {
    await latency(180)
    if (target.scope === 'remote') {
      return { ok: false, summary: 'Remote direct pane control is disabled in this mock.', error: 'remote-direct-disabled' }
    }
    return { ok: true, summary: `Mock direct text ${submit ? 'submitted' : 'sent'} to ${target.address}.` }
  }

  async sendDirectKeys(target: TargetRef, keys: string[]): Promise<ActionResult> {
    await latency(180)
    if (target.scope === 'remote') {
      return { ok: false, summary: 'Remote direct pane control is disabled in this mock.', error: 'remote-direct-disabled' }
    }
    return { ok: true, summary: `Mock direct keys [${keys.join(', ')}] sent to ${target.address}.` }
  }

  async sendPaneCapture(sourceName: string, targetName: string): Promise<ActionResult> {
    await latency(180)
    const messageText = `### Mock Pane Capture Snapshot from ${sourceName}\n` +
      `- **Pane:** %0\n` +
      `- **Session:** mock-session\n` +
      `- **Copy Mode:** Inactive\n` +
      `- **Captured At:** ${new Date().toISOString()}\n` +
      `\n\`\`\`\n[mock pane history output for dev exploration]\n\`\`\`\n`
    const message = {
      id: nextMockId('pane-cap'),
      conversationKey: sourceName,
      direction: 'inbound' as const,
      author: sourceName,
      body: messageText,
      createdAt: new Date().toISOString(),
      deliveryState: 'received' as const,
    }
    this.messages[sourceName] = [...(this.messages[sourceName] ?? []), message]
    return { ok: true, summary: `Mock snapshot successfully sent to ${targetName}` }
  }

  async listSavedAgents(): Promise<SavedAgent[]> {
    await latency()
    return [
      {
        name: 'jetski',
        agentCommand: 'jetski-cli',
        agentArgs: [],
        description: '专家智能编程助手 pair programming with DeepMind researchers',
      },
      {
        name: 'pi',
        agentCommand: 'pi-agent',
        agentArgs: ['--role', 'reviewer'],
        description: 'Local developer assistant for Nix and shell scripting',
      },
    ]
  }

  async spinAgent(configName: string, directory: string): Promise<ActionResult> {
    await latency(180)
    return { ok: true, summary: `Mock spun agent '${configName}' successfully inside ${directory}` }
  }

  async selectLocalDirectory(): Promise<string | null> {
    await latency()
    return '/mock/local/projects/broccoli-comms'
  }

  onTrackerEvents(_callback: (events: any[]) => void): () => void {
    return () => {}
  }
}
