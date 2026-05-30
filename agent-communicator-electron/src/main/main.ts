import { app, BrowserWindow, shell } from 'electron'
import { join } from 'node:path'
import { registerMockIpcHandlers, startTrackerEventLoop, stopTrackerEventLoop } from './ipc'

function createWindow(): void {
  const mainWindow = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 980,
    minHeight: 680,
    title: 'Broccoli Comms — Mock Agent Communicator',
    backgroundColor: '#0b1020',
    webPreferences: {
      preload: join(__dirname, '../preload/preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }

  // Start background wait_events loop for pushes!
  void startTrackerEventLoop(mainWindow.webContents)
}

app.whenReady().then(() => {
  registerMockIpcHandlers()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  stopTrackerEventLoop()
  if (process.platform !== 'darwin') app.quit()
})
