import type { ReactNode } from 'react'
import type { RuntimeStatus } from '../../shared/contracts'
import { RuntimeStatusBar } from './RuntimeStatusBar'

interface Props {
  agents: ReactNode
  main: ReactNode
  details: ReactNode
  status: RuntimeStatus | null
  detailsOpen: boolean
  onCloseDetails: () => void
}

export function AppShell({ agents, main, details, status, detailsOpen, onCloseDetails }: Props) {
  return (
    <>
      <div className="menubar">
        <span>File</span>
        <span>Edit</span>
        <span>View</span>
        <span>Window</span>
      </div>

      <div className={`app ${detailsOpen ? 'details-open' : ''}`}>
        {agents}
        <main className="conv">{main}</main>
        <aside className="details" aria-hidden={!detailsOpen}>
          <div className="details-head">
            <h3>Agent details</h3>
            <button className="details-close" title="Close panel" onClick={onCloseDetails}>
              ×
            </button>
          </div>
          <div className="details-body">{details}</div>
        </aside>
        <RuntimeStatusBar status={status} />
      </div>
    </>
  )
}
