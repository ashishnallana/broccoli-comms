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
  ipcMain.handle(IPC_CHANNELS.sendDirectText, async (_event, target: TargetRef, text: string, submit: boolean) => {
    const tracker = trackerClient()
    if (tracker) return tracker.sendDirectText(target, text, submit)
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
    const tracker = trackerClient()
    if (tracker) return tracker.sendDirectKeys(target, keys)
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
  ipcMain.handle('tracker-wait-events', async (_event, clientId: string, cursor: number, watchlist: string[], leaseSeconds: number) => {
    const tracker = trackerClient()
    if (tracker) return tracker.waitEvents(clientId, cursor, watchlist, leaseSeconds)
    return { events: [], lastSeq: 0 }
  })
  ipcMain.on('tracker-update-watchlist', (_event, watchlist: string[]) => {
    activeWatchlist = watchlist
  })
}

let activeWatchlist: string[] = []
let eventLoopRunning = false
let eventLoopCancel = false

export async function startTrackerEventLoop(webContents: Electron.WebContents) {
  if (eventLoopRunning) return
  eventLoopRunning = true
  eventLoopCancel = false

  let since = 0
  while (!eventLoopCancel) {
    const tracker = trackerClient()
    if (!tracker) {
      await new Promise((resolve) => setTimeout(resolve, 3000))
      continue
    }

    try {
      const clientId = tracker.selfAgentName
      const result = await tracker.waitEvents(clientId, since, activeWatchlist, 60)
      if (eventLoopCancel) break

      if (result.reset || result.gap) {
        since = 0
        webContents.send('tracker-reset-required')
        continue
      }

      if (result && result.events && result.events.length > 0) {
        webContents.send(IPC_CHANNELS.onTrackerEvents, result.events)
      }
      since = result.lastSeq || since
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      if (msg.includes('cursor_expired')) {
        since = 0
        webContents.send('tracker-reset-required')
      }
      await new Promise((resolve) => setTimeout(resolve, 3000))
    }
  }
  eventLoopRunning = false
}

export function stopTrackerEventLoop() {
  eventLoopCancel = true
}
