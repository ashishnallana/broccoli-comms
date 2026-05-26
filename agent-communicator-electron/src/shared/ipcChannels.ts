export const IPC_CHANNELS = {
  runtimeStatus: 'broccoli-mock:runtime-status',
  listAgents: 'broccoli-mock:list-agents',
  listMessages: 'broccoli-mock:list-messages',
  sendMessage: 'broccoli-mock:send-message',
  sendDirectText: 'broccoli-mock:send-direct-text',
  sendDirectKeys: 'broccoli-mock:send-direct-keys',
  sendPaneCapture: 'broccoli-mock:send-pane-capture',
} as const

export type IpcChannel = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS]
