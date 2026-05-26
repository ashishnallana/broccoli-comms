import type { ReactNode } from 'react'
import type { AgentSummary, RuntimeStatus, SavedAgent } from '../../shared/contracts'
import { RuntimeStatusBar } from './RuntimeStatusBar'
import { ShortcutsPanel } from './ShortcutsPanel'
import { CommandPalette } from './CommandPalette'
import { LaunchAgentModal } from './LaunchAgentModal'

interface Props {
  agents: ReactNode
  main: ReactNode
  details: ReactNode
  status: RuntimeStatus | null
  detailsOpen: boolean
  onCloseDetails: () => void

  shortcutsOpen: boolean
  onOpenShortcuts: () => void
  onCloseShortcuts: () => void

  paletteOpen: boolean
  onOpenPalette: () => void
  onClosePalette: () => void

  agentsRaw: AgentSummary[]
  onSelectAgent: (agent: AgentSummary) => void

  launchModalOpen: boolean
  onCloseLaunchModal: () => void
  onLaunchAgent: (configName: string, directory: string) => Promise<{ ok: boolean; error?: string }>
  onBrowseDirectory: () => Promise<string | null>
  savedAgents: SavedAgent[]
}

export function AppShell({
  agents,
  main,
  details,
  status,
  detailsOpen,
  onCloseDetails,
  shortcutsOpen,
  onOpenShortcuts,
  onCloseShortcuts,
  paletteOpen,
  onOpenPalette,
  onClosePalette,
  agentsRaw,
  onSelectAgent,
  launchModalOpen,
  onCloseLaunchModal,
  onLaunchAgent,
  onBrowseDirectory,
  savedAgents,
}: Props) {
  return (
    <>
      <div className="menubar">
        <span style={{ cursor: 'pointer' }} onClick={onOpenShortcuts}>Help</span>
        <div className="menubar-search" id="openPalette" onClick={onOpenPalette}>
          <svg className="menubar-search-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <circle cx="7" cy="7" r="5" />
            <line x1="11" y1="11" x2="14" y2="14" strokeLinecap="round" />
          </svg>
          <span>Jump to channel, agent…</span>
          <kbd>⌘</kbd><kbd>K</kbd>
        </div>
      </div>

      <div className={`app ${detailsOpen ? 'details-open' : ''}`}>
        {agents}
        <main className="main">{main}</main>
        <aside className="details" aria-hidden={!detailsOpen}>
          <div className="details-head">
            <h3>Agent details</h3>
            <button className="details-close" title="Close panel" onClick={onCloseDetails}>
              ×
            </button>
          </div>
          <div className="details-body">{details}</div>
        </aside>
        <RuntimeStatusBar status={status} onOpenShortcuts={onOpenShortcuts} />
      </div>

      <CommandPalette open={paletteOpen} agents={agentsRaw} onSelectAgent={onSelectAgent} onClose={onClosePalette} />
      <ShortcutsPanel open={shortcutsOpen} onClose={onCloseShortcuts} />
      <LaunchAgentModal
        open={launchModalOpen}
        savedAgents={savedAgents}
        onClose={onCloseLaunchModal}
        onLaunch={onLaunchAgent}
        onBrowseDirectory={onBrowseDirectory}
      />
    </>
  )
}
