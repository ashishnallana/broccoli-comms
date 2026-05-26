import { ipcMain } from 'electron'
import { IPC_CHANNELS } from '../shared/ipcChannels'
import type { TargetRef } from '../shared/contracts'
import { mockAgents, mockMessages, mockRuntimeStatus } from '../test/fixtures'
import { LocalTrackerClient, resolveTrackerSocket } from './trackerClient'

let cachedTracker: { socketPath: string; client: LocalTrackerClient } | undefined

function trackerClient(): LocalTrackerClient | undefined {
  const socketPath = resolveTrackerSocket()
  if (!socketPath) {
    cachedTracker = undefined
    return undefined
  }
  if (cachedTracker?.socketPath === socketPath) return cachedTracker.client
  cachedTracker = { socketPath, client: new LocalTrackerClient(socketPath) }
  return cachedTracker.client
}

export function registerMockIpcHandlers(): void {
  ipcMain.handle(IPC_CHANNELS.runtimeStatus, async () => {
    const tracker = trackerClient()
    return tracker ? tracker.getStatus() : mockRuntimeStatus
  })
  ipcMain.handle(IPC_CHANNELS.listAgents, async () => {
    const tracker = trackerClient()
    return tracker ? tracker.listAgents() : mockAgents
  })
  ipcMain.handle(IPC_CHANNELS.listMessages, async (_event, conversationKey: string) => {
    const tracker = trackerClient()
    return tracker ? tracker.listMessages(conversationKey) : (mockMessages[conversationKey] ?? [])
  })
  ipcMain.handle(IPC_CHANNELS.sendMessage, async (_event, target: TargetRef, body: string) => {
    const tracker = trackerClient()
    if (tracker) return tracker.sendMessage(target, body)

    const message = {
      id: `mock-out-${Date.now()}`,
      conversationKey: target.address,
      direction: 'outbound' as const,
      author: 'you',
      body,
      createdAt: new Date().toISOString(),
      deliveryState: 'delivered' as const,
    }
    mockMessages[message.conversationKey] = [...(mockMessages[message.conversationKey] ?? []), message]
    return { ok: true, message }
  })
  ipcMain.handle(IPC_CHANNELS.sendDirectText, async (_event, target: TargetRef, _text: string, submit: boolean) => {
    if (trackerClient()) {
      return { ok: false, summary: 'Direct pane control is not wired for tracker Simple View yet.', error: 'direct-not-implemented' }
    }
    return {
      ok: target.scope === 'local',
      summary:
        target.scope === 'local'
          ? `Mock direct text ${submit ? 'submitted' : 'sent'} to ${target.address}`
          : 'Remote direct pane control is disabled in the mock.',
      error: target.scope === 'local' ? undefined : 'remote-direct-disabled',
    }
  })
  ipcMain.handle(IPC_CHANNELS.sendDirectKeys, async (_event, target: TargetRef, keys: string[]) => {
    if (trackerClient()) {
      return { ok: false, summary: 'Direct pane control is not wired for tracker Simple View yet.', error: 'direct-not-implemented' }
    }
    return {
      ok: target.scope === 'local',
      summary:
        target.scope === 'local'
          ? `Mock direct keys [${keys.join(', ')}] sent to ${target.address}`
          : 'Remote direct pane control is disabled in the mock.',
      error: target.scope === 'local' ? undefined : 'remote-direct-disabled',
    }
  })
}
