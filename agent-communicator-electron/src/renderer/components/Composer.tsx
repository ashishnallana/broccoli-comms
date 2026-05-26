import { useState } from 'react'
import type { AgentSummary, ComposerMode } from '../../shared/contracts'
import { composerActionLabel, composerPlaceholder, directModeWarning } from '../features/composer/composerActions'
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
  const directBlocked = direct && !agent.canDirectControl
  const warning = directModeWarning(mode)

  async function submit() {
    const trimmed = body.trim()
    if (!trimmed || directBlocked) return
    await onSubmit(trimmed)
    setBody('')
  }

  return (
    <section className={`composer-wrap ${direct ? 'direct' : ''} ${directBlocked ? 'blocked' : ''}`}>
      <div className="mode-row">
        <ActionModePicker mode={mode} agent={agent} onModeChange={onModeChange} />
        <div className={`composer-status ${direct ? 'warn' : ''}`}>{status}</div>
      </div>
      {warning || directBlocked ? (
        <div className={directBlocked ? 'direct-warning blocked' : 'direct-warning'}>
          <strong>{directBlocked ? 'Remote direct control locked' : 'Mock pane-control mode'}</strong>
          <span>{directBlocked ? 'Direct Text and Direct Keys are disabled for remote fixture agents.' : warning}</span>
        </div>
      ) : null}
      <div className="composer-grid">
        <textarea
          value={body}
          placeholder={directBlocked ? 'Remote direct pane control is disabled in this mock.' : composerPlaceholder(mode)}
          disabled={directBlocked}
          onChange={(event) => setBody(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
              event.preventDefault()
              void submit()
            }
          }}
        />
        <button className={direct ? 'send direct' : 'send'} disabled={directBlocked} onClick={() => void submit()}>
          {composerActionLabel(mode)}
        </button>
      </div>
    </section>
  )
}
