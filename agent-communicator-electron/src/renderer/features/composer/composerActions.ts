import type { ComposerMode } from '../../../shared/contracts'

export function composerPlaceholder(mode: ComposerMode): string {
  switch (mode) {
    case 'message':
      return 'Type a normal inbox message…'
    case 'directText':
      return 'Mock direct text to a local pane…'
    case 'directKeys':
      return 'Enter symbolic keys, e.g. C-c Enter…'
  }
}

export function composerActionLabel(mode: ComposerMode): string {
  if (mode === 'directText') return 'Run text'
  if (mode === 'directKeys') return 'Run keys'
  return 'Send'
}

export function defaultComposerStatus(mode: ComposerMode): string {
  switch (mode) {
    case 'message':
      return 'Message mode: normal mock inbox delivery.'
    case 'directText':
      return 'Direct Text: local-only mock pane control. No message history is created.'
    case 'directKeys':
      return 'Direct Keys: local-only symbolic key sequence. No message history is created.'
  }
}

export function directModeWarning(mode: ComposerMode): string | undefined {
  if (mode === 'directText') return 'Warning: Direct Text simulates writing text into a local agent pane. It is not an inbox message.'
  if (mode === 'directKeys') return 'Warning: Direct Keys simulates pane key presses. Use symbolic keys such as C-c or Enter.'
  return undefined
}
