import type { RuntimeStatus } from '../../shared/contracts'
import { RuntimeStatusBar } from './RuntimeStatusBar'

interface Props {
  status: RuntimeStatus | null
}

export function Sidebar({ status }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo">🥦</div>
        <div>
          <strong>Agent Communicator</strong>
          <span>Electron mock</span>
        </div>
      </div>
      <RuntimeStatusBar status={status} onOpenShortcuts={() => {}} />
      <nav className="nav-list" aria-label="Mock navigation">
        <button className="active">
          <span>Agents</span>
          <small>local + remote fixtures</small>
        </button>
        <button>
          <span>Saved prompts</span>
          <small>planned mock area</small>
        </button>
        <button>
          <span>Settings / Runtime</span>
          <small>mock health controls later</small>
        </button>
      </nav>
      <div className="sidebar-note">
        <strong>Dev-only boundary</strong>
        <span>No tracker socket, registry calls, tmux control, Broccoli runtime, or persistence is used.</span>
      </div>
    </aside>
  )
}
