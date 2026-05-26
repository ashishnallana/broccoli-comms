import type { RuntimeStatus } from '../../shared/contracts'
import { healthLabel } from '../lib/format'
import { formatTime } from '../lib/time'

interface Props {
  status: RuntimeStatus | null
}

export function RuntimeStatusBar({ status }: Props) {
  if (!status) return <div className="runtime-card skeleton">Loading mock runtime…</div>

  return (
    <div className="runtime-card">
      <div className="runtime-heading">
        <div>
          <div className="eyebrow">Runtime</div>
          <strong>{status.label}</strong>
        </div>
        <span className="mock-pill">dev mock</span>
      </div>
      <div className="runtime-chips">
        <span className={`chip ${status.health}`}>runtime {healthLabel(status.health)}</span>
        <span className={`chip ${status.tracker}`}>tracker {healthLabel(status.tracker)}</span>
        <span className={`chip ${status.registry}`}>registry {healthLabel(status.registry)}</span>
        <span className={`chip ${status.tmux}`}>tmux {healthLabel(status.tmux)}</span>
      </div>
      <div className="runtime-footnote">Updated {formatTime(status.updatedAt)} from local fixtures.</div>
      <ul className="runtime-notes">
        {status.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </div>
  )
}
