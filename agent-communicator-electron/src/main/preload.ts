import { contextBridge, ipcRenderer } from 'electron'
import { IPC_CHANNELS } from '../shared/ipcChannels'
import type { ActionResult, AgentSummary, Message, RuntimeStatus, SavedAgent, SendResult, TargetRef } from '../shared/contracts'

const api = {
  getStatus: (): Promise<RuntimeStatus> => ipcRenderer.invoke(IPC_CHANNELS.runtimeStatus),
  listAgents: (): Promise<AgentSummary[]> => ipcRenderer.invoke(IPC_CHANNELS.listAgents),
  listMessages: (conversationKey: string): Promise<Message[]> => ipcRenderer.invoke(IPC_CHANNELS.listMessages, conversationKey),
  sendMessage: (target: TargetRef, body: string): Promise<SendResult> => ipcRenderer.invoke(IPC_CHANNELS.sendMessage, target, body),
  sendDirectText: (target: TargetRef, text: string, submit: boolean): Promise<ActionResult> =>
    ipcRenderer.invoke(IPC_CHANNELS.sendDirectText, target, text, submit),
  sendDirectKeys: (target: TargetRef, keys: string[]): Promise<ActionResult> =>
    ipcRenderer.invoke(IPC_CHANNELS.sendDirectKeys, target, keys),
  sendPaneCapture: (sourceName: string, targetName: string): Promise<ActionResult> =>
    ipcRenderer.invoke(IPC_CHANNELS.sendPaneCapture, sourceName, targetName),
  listSavedAgents: (): Promise<SavedAgent[]> => ipcRenderer.invoke(IPC_CHANNELS.listSavedAgents),
  spinAgent: (configName: string, directory: string): Promise<ActionResult> =>
    ipcRenderer.invoke(IPC_CHANNELS.spinAgent, configName, directory),
  selectLocalDirectory: (): Promise<string | null> => ipcRenderer.invoke(IPC_CHANNELS.selectLocalDirectory),
  onTrackerEvents: (callback: (events: any[]) => void) => {
    const subscription = (_event: any, events: any[]) => callback(events)
    ipcRenderer.on(IPC_CHANNELS.onTrackerEvents, subscription)
    return () => {
      ipcRenderer.removeListener(IPC_CHANNELS.onTrackerEvents, subscription)
    }
  },
}

contextBridge.exposeInMainWorld('broccoliCommsMock', api)

export type BroccoliCommsMockApi = typeof api
