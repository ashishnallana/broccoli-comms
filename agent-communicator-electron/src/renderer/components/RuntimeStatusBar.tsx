import { useEffect, useState } from 'react'
import type { RuntimeHealth, RuntimeStatus } from '../../shared/contracts'
import { healthLabel } from '../lib/format'

interface Props {
  status: RuntimeStatus | null
  onOpenShortcuts: () => void
}

function dotClass(health: RuntimeHealth | undefined): string {
  if (health === 'healthy') return 'healthy'
  if (health === 'degraded') return 'warn'
  if (health === 'offline') return 'error'
  return 'muted'
}

export function RuntimeStatusBar({ status, onOpenShortcuts }: Props) {
  const [open, setOpen] = useState(false)

  const runtimeHealth = status?.health ?? 'offline'
  const trackerHealth = status?.tracker ?? 'offline'
  const registryHealth = status?.registry ?? 'offline'
  const tmuxHealth = status?.tmux ?? 'offline'
  const mode = status?.mode ?? 'mock'

  return (
    <footer className="statusbar">
      <div className="sb-item clickable" title="Runtime status" onClick={() => setOpen((value) => !value)}>
        <span className={`sb-dot ${dotClass(runtimeHealth)} ${runtimeHealth !== 'offline' ? 'sb-pulse' : ''}`} />
        <span className="sb-label">Runtime</span>
        <span className={`sb-value ${dotClass(runtimeHealth)}`}>{status ? healthLabel(runtimeHealth) : 'loading'}</span>

        <div className={`sb-popover ${open ? 'open' : ''}`} onClick={(event) => event.stopPropagation()}>
          <div className="sb-popover-title">Runtime status</div>
          <div className="sb-popover-row">
            <span className="sb-popover-key"><span className={`sb-dot ${dotClass(trackerHealth)}`} /> Tracker socket</span>
            <span className={`sb-popover-val ${dotClass(trackerHealth)}`}>{healthLabel(trackerHealth)}</span>
          </div>
          <div className="sb-popover-row">
            <span className="sb-popover-key"><span className={`sb-dot ${dotClass(registryHealth)}`} /> Registry</span>
            <span className={`sb-popover-val ${dotClass(registryHealth)}`}>{healthLabel(registryHealth)}</span>
          </div>
          <div className="sb-popover-row">
            <span className="sb-popover-key"><span className={`sb-dot ${dotClass(tmuxHealth)}`} /> tmux server</span>
            <span className={`sb-popover-val ${dotClass(tmuxHealth)}`}>{healthLabel(tmuxHealth)}</span>
          </div>
          <div className="sb-popover-row">
            <span className="sb-popover-key"><span className="sb-dot healthy" /> Inbox identity</span>
            <span className="sb-popover-val">agent-communicator</span>
          </div>
          <div className="sb-popover-hint">
            {status?.notes?.[0] ?? 'Renderer stays isolated; main process owns tracker IPC.'}
          </div>
        </div>
      </div>

      <div className="sb-divider" />
      <div className="sb-item" title="Local agent-tracker socket">
        <span className="sb-label">Tracker</span>
        <span className="sb-value">{healthLabel(trackerHealth)}</span>
      </div>
      <div className="sb-item" title="tmux server status">
        <span className="sb-label">tmux</span>
        <span className={`sb-value ${dotClass(tmuxHealth)}`}>{healthLabel(tmuxHealth)}</span>
      </div>
      <div className="sb-item" title="Remote registry">
        <span className="sb-label">Registry</span>
        <span className={`sb-value ${dotClass(registryHealth)}`}>{healthLabel(registryHealth)}</span>
      </div>

      <div className="sb-spacer" />
      <div className="sb-item" title="Active view">
        <span className="sb-value">{status?.label ?? 'Loading runtime'}</span>
      </div>
      <div className="sb-divider" />
      <div className="sb-item" title="Runtime mode">
        <span className="sb-dot muted" />
        <span className="sb-value muted">{mode === 'tracker' ? 'Tracker simple' : 'Dev mock'}</span>
      </div>
      <div className="sb-divider" />
      <div className="sb-item clickable" id="openShortcuts" title="Keyboard shortcuts" onClick={onOpenShortcuts}>
        <span className="sb-label">Shortcuts</span>
        <kbd>?</kbd>
      </div>
    </footer>
  )
}
