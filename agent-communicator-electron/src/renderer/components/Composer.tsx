import { useState } from 'react'
import type { AgentSummary, ComposerMode } from '../../shared/contracts'
import { composerActionLabel, composerPlaceholder } from '../features/composer/composerActions'
import { ActionModePicker } from './ActionModePicker'

interface Props {
  agent: AgentSummary
  mode: ComposerMode
  status: string
  onModeChange: (mode: ComposerMode) => void
  onSubmit: (body: string) => Promise<void>
}

export function Composer({ agent, mode, status, onModeChange, onSubmit }: Props) {
  const [body, setBody] = useState('')
  const direct = mode !== 'message'
  const directBlocked = direct

  async function submit() {
    const trimmed = body.trim()
    if (!trimmed || directBlocked) return
    await onSubmit(trimmed)
    setBody('')
  }

  return (
    <div className="composer">
      <div className="composer-tabs">
        <ActionModePicker mode={mode} agent={agent} onModeChange={onModeChange} />
        <div className="composer-status">
          <span className="ok">●</span> {status}
        </div>
      </div>
      <div className="composer-input-row">
        <textarea
          className="composer-input"
          value={body}
          placeholder={directBlocked ? 'Direct pane control is locked.' : composerPlaceholder(mode)}
          disabled={directBlocked}
          onChange={(event) => setBody(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void submit()
            }
          }}
        />
        <button className="btn primary send" disabled={directBlocked || !body.trim()} onClick={() => void submit()}>
          {composerActionLabel(mode)}
        </button>
      </div>
    </div>
  )
}
