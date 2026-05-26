import { ipcMain } from 'electron'
import { IPC_CHANNELS } from '../shared/ipcChannels'
import type { TargetRef } from '../shared/contracts'
import { mockAgents, mockMessages, mockRuntimeStatus } from '../test/fixtures'

export function registerMockIpcHandlers(): void {
  ipcMain.handle(IPC_CHANNELS.runtimeStatus, async () => mockRuntimeStatus)
  ipcMain.handle(IPC_CHANNELS.listAgents, async () => mockAgents)
  ipcMain.handle(IPC_CHANNELS.listMessages, async (_event, conversationKey: string) => mockMessages[conversationKey] ?? [])
  ipcMain.handle(IPC_CHANNELS.sendMessage, async (_event, target: TargetRef, body: string) => {
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
  ipcMain.handle(IPC_CHANNELS.sendDirectText, async (_event, target: TargetRef, _text: string, submit: boolean) => ({
    ok: target.scope === 'local',
    summary:
      target.scope === 'local'
        ? `Mock direct text ${submit ? 'submitted' : 'sent'} to ${target.address}`
        : 'Remote direct pane control is disabled in the mock.',
    error: target.scope === 'local' ? undefined : 'remote-direct-disabled',
  }))
  ipcMain.handle(IPC_CHANNELS.sendDirectKeys, async (_event, target: TargetRef, keys: string[]) => ({
    ok: target.scope === 'local',
    summary:
      target.scope === 'local'
        ? `Mock direct keys [${keys.join(', ')}] sent to ${target.address}`
        : 'Remote direct pane control is disabled in the mock.',
    error: target.scope === 'local' ? undefined : 'remote-direct-disabled',
  }))
}
