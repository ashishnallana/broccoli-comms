import { useEffect, useLayoutEffect, useRef } from 'react'
import type { AgentSummary, ComposerMode } from '../../shared/contracts'
import { composerActionLabel, composerPlaceholder } from '../features/composer/composerActions'
import { ActionModePicker } from './ActionModePicker'

interface Props {
  agent: AgentSummary
  mode: ComposerMode
  status: string
  body: string
  onBodyChange: (body: string) => void
  onModeChange: (mode: ComposerMode) => void
  onSubmit: (body: string) => Promise<void>
}

export function Composer({ agent, mode, status, body, onBodyChange, onModeChange, onSubmit }: Props) {
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  useLayoutEffect(() => {
    const input = inputRef.current
    if (!input) return
    input.style.height = '0px'
    input.style.height = `${Math.min(input.scrollHeight, 116)}px`
  }, [body])

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    input.focus({ preventScroll: true })
    input.setSelectionRange(input.value.length, input.value.length)
  }, [agent.conversationKey])

  async function submit() {
    const trimmed = body.trim()
    if (!trimmed) return
    if (mode === 'directKeys') {
      const keys = trimmed.split(/[\s,]+/).filter(Boolean)
      await onSubmit(JSON.stringify({ type: 'keys', keys }))
    } else {
      await onSubmit(trimmed)
    }
    onBodyChange('')
  }

  async function handleSendDirectKey(keyName: string) {
    await onSubmit(JSON.stringify({ type: 'keys', keys: [keyName] }))
  }

  return (
    <div className="composer">
      <div className="composer-tabs">
        <ActionModePicker mode={mode} agent={agent} onModeChange={onModeChange} />
        <div className="composer-status">
          <span className="ok">●</span> {status}
        </div>
      </div>

      {/* Direct Keys Keyboard Matrix */}
      {mode === 'directKeys' && (
        <div
          className="quick-keys-row"
          style={{
            display: 'flex',
            gap: '6px',
            marginTop: '2px',
            marginBottom: '8px',
            flexWrap: 'wrap',
          }}
        >
          {['Escape', 'Enter', 'C-c', 'Tab', 'Up', 'Down', 'Left', 'Right'].map((keyName) => (
            <button
              key={keyName}
              className="btn"
              style={{
                height: '24px',
                padding: '0 10px',
                fontSize: '11px',
                fontFamily: '"JetBrains Mono", monospace',
                background: 'var(--surface-soft)',
                borderColor: 'var(--hairline-strong)',
                borderRadius: 'var(--r-sm)',
                color: 'var(--primary)',
                fontWeight: 700,
                cursor: 'pointer',
              }}
              onClick={() => handleSendDirectKey(keyName)}
            >
              {keyName === 'C-c' ? 'Ctrl+C' : keyName}
            </button>
          ))}
        </div>
      )}

      <div className="composer-input-row">
        <textarea
          ref={inputRef}
          className="composer-input"
          value={body}
          placeholder={composerPlaceholder(mode)}
          onChange={(event) => onBodyChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void submit()
            }
          }}
        />
        <button className="btn primary send" disabled={!body.trim() && mode !== 'directKeys'} onClick={() => void submit()}>
          {composerActionLabel(mode)}
        </button>
      </div>
    </div>
  )
}
