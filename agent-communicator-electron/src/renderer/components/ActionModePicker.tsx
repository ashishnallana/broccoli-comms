import type { AgentSummary, ComposerMode } from '../../shared/contracts'

interface Props {
  mode: ComposerMode
  agent: AgentSummary
  onModeChange: (mode: ComposerMode) => void
}

const modes: Array<{ value: ComposerMode; label: string; hint: string; direct?: boolean }> = [
  { value: 'message', label: 'Message', hint: 'Inbox' },
  { value: 'directText', label: 'Direct Text', hint: 'Pane text', direct: true },
  { value: 'directKeys', label: 'Direct Keys', hint: 'Pane keys', direct: true },
]

export function ActionModePicker({ mode, agent, onModeChange }: Props) {
  return (
    <div className="mode-picker" role="group" aria-label="Composer mode">
      {modes.map((item) => {
        const disabled = item.direct && !agent.canDirectControl
        return (
          <button
            key={item.value}
            className={`${mode === item.value ? 'active' : ''} ${item.direct ? 'direct' : ''}`}
            disabled={disabled}
            title={disabled ? 'Remote direct pane control is disabled in this mock' : item.hint}
            onClick={() => onModeChange(item.value)}
          >
            <span>{item.label}</span>
            <small>{disabled ? 'locked' : item.hint}</small>
          </button>
        )
      })}
    </div>
  )
}
