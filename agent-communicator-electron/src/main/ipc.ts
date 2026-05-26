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
  ipcMain.handle(IPC_CHANNELS.sendPaneCapture, async (_event, sourceName: string, targetName: string) => {
    const tracker = trackerClient()
    if (tracker) return tracker.sendPaneCapture(sourceName, targetName)

    // Mock implementation
    const messageText = `### Mock Pane Capture Snapshot from ${sourceName}\n` +
      `- **Pane:** %0\n` +
      `- **Session:** mock-session\n` +
      `- **Copy Mode:** Inactive\n` +
      `- **Captured At:** ${new Date().toISOString()}\n` +
      `\n\`\`\`\n[mock pane history output for dev exploration]\n\`\`\`\n`
    const message = {
      id: `mock-pane-cap-${Date.now()}`,
      conversationKey: sourceName,
      direction: 'inbound' as const,
      author: sourceName,
      body: messageText,
      createdAt: new Date().toISOString(),
      deliveryState: 'received' as const,
    }
    mockMessages[sourceName] = [...(mockMessages[sourceName] ?? []), message]
    return { ok: true, summary: `Mock snapshot successfully sent to ${targetName}` }
  })
  ipcMain.handle(IPC_CHANNELS.listSavedAgents, async () => {
    const tracker = trackerClient()
    if (tracker) return tracker.listSavedAgents()

    return [
      { name: 'jetski', agentCommand: 'jetski-cli', agentArgs: [], description: '专家智能编程助手 pair programming with DeepMind researchers' },
      { name: 'pi', agentCommand: 'pi-agent', agentArgs: ['--role', 'reviewer'], description: 'Local developer assistant for Nix and shell scripting' },
    ]
  })
  ipcMain.handle(IPC_CHANNELS.spinAgent, async (_event, configName: string, directory: string) => {
    const tracker = trackerClient()
    if (tracker) return tracker.spinAgent(configName, directory)

    return { ok: true, summary: `Mock spun agent '${configName}' successfully inside ${directory}` }
  })
  ipcMain.handle(IPC_CHANNELS.selectLocalDirectory, async () => {
    const { dialog } = require('electron')
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      title: 'Select Agent Working Directory',
      buttonLabel: 'Select Directory',
    })
    return result.filePaths[0] || null
  })
}
