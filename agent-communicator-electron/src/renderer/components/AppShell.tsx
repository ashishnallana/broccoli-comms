import type { ReactNode } from 'react'

interface Props {
  sidebar: ReactNode
  agents: ReactNode
  main: ReactNode
  details: ReactNode
}

export function AppShell({ sidebar, agents, main, details }: Props) {
  return (
    <div className="app-shell">
      {sidebar}
      {agents}
      <main className="main-pane">{main}</main>
      <aside className="details-pane">{details}</aside>
    </div>
  )
}
