import type { ComposerMode } from '../../../shared/contracts'

export function composerPlaceholder(mode: ComposerMode): string {
  switch (mode) {
    case 'message':
      return 'Type a normal inbox message…'
    case 'directText':
      return 'Direct Text is locked in tracker simple view…'
    case 'directKeys':
      return 'Direct Keys is locked in tracker simple view…'
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
      return 'Message mode: normal inbox delivery.'
    case 'directText':
      return 'Direct Text is locked in tracker simple view.'
    case 'directKeys':
      return 'Direct Keys is locked in tracker simple view.'
  }
}

export function directModeWarning(mode: ComposerMode): string | undefined {
  if (mode === 'directText') return 'Direct Text is locked; no pane text is sent from this UI.'
  if (mode === 'directKeys') return 'Direct Keys is locked; no pane key sequence is sent from this UI.'
  return undefined
}
