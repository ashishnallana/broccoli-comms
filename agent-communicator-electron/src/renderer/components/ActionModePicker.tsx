import type { AgentSummary, ComposerMode } from '../../shared/contracts'

interface Props {
  mode: ComposerMode
  agent: AgentSummary
  onModeChange: (mode: ComposerMode) => void
}

const modes: Array<{ value: ComposerMode; label: string; hint: string; direct?: boolean }> = [
  { value: 'message', label: 'Message', hint: 'INBOX' },
  { value: 'directText', label: 'Direct Text', hint: 'LOCKED', direct: true },
  { value: 'directKeys', label: 'Direct Keys', hint: 'LOCKED', direct: true },
]

export function ActionModePicker({ mode, onModeChange }: Props) {
  return (
    <div className="tab-group" role="group" aria-label="Composer mode">
      {modes.map((item) => {
        const disabled = Boolean(item.direct)
        return (
          <button
            key={item.value}
            className={`tab ${mode === item.value ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
            disabled={disabled}
            title={disabled ? 'Direct pane control is locked in tracker simple view' : item.hint}
            onClick={() => onModeChange(item.value)}
          >
            {item.label}
            <span className="tab-sub">{item.hint}</span>
          </button>
        )
      })}
    </div>
  )
}
