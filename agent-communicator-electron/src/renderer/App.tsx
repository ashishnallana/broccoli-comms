import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { AgentSummary, ComposerMode, Message, RuntimeStatus } from '../shared/contracts'
import { AgentList } from './components/AgentList'
import { AppShell } from './components/AppShell'
import { Composer } from './components/Composer'
import { ConversationView } from './components/ConversationView'
import { EmptyState } from './components/EmptyState'
import { targetForAgent } from './features/agents/agentStore'
import { defaultComposerStatus } from './features/composer/composerActions'
import { optimisticMessage } from './features/conversations/conversationStore'
import { createRuntimeClient } from './features/runtime/runtimeClient'

export function App() {
  const runtime = useMemo(() => createRuntimeClient(), [])
  const [status, setStatus] = useState<RuntimeStatus | null>(null)
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [selectedId, setSelectedId] = useState<string>()
  const [messages, setMessages] = useState<Message[]>([])
  const [mode, setMode] = useState<ComposerMode>('message')
  const [composerStatus, setComposerStatus] = useState(defaultComposerStatus('message'))
  const [loading, setLoading] = useState(true)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [visibleAgents, setVisibleAgents] = useState<AgentSummary[]>([])
  const [agentFilterActive, setAgentFilterActive] = useState(false)

  // Modal & overlay visibility states
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)

  const directStatusResetTimer = useRef<number | undefined>(undefined)
  const modeRef = useRef<ComposerMode>(mode)
  const selectedIdRef = useRef<string | undefined>(selectedId)

  const selectedAgent = agents.find((agent) => agent.id === selectedId)

  function clearDirectStatusReset() {
    if (directStatusResetTimer.current !== undefined) {
      window.clearTimeout(directStatusResetTimer.current)
      directStatusResetTimer.current = undefined
    }
  }

  useEffect(() => {
    modeRef.current = mode
  }, [mode])

  useEffect(() => {
    selectedIdRef.current = selectedId
  }, [selectedId])

  useEffect(() => {
    return () => clearDirectStatusReset()
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      const [runtimeStatus, agentList] = await Promise.all([runtime.getStatus(), runtime.listAgents()])
      if (cancelled) return
      setStatus(runtimeStatus)
      setAgents(agentList)
      setSelectedId(agentList[0]?.id)
      setLoading(false)
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [runtime])

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined
    async function loadMessages() {
      if (!selectedAgent) {
        setMessages([])
        return
      }
      const nextMessages = await runtime.listMessages(selectedAgent.conversationKey)
      if (!cancelled) setMessages(nextMessages)
    }
    void loadMessages()
    timer = window.setInterval(() => void loadMessages(), 3000)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearInterval(timer)
    }
  }, [runtime, selectedAgent])

  useEffect(() => {
    if (selectedAgent && mode !== 'message') {
      setMode('message')
      setComposerStatus('Direct pane control is locked; reset to Message mode.')
    }
  }, [mode, selectedAgent])

  function updateMode(nextMode: ComposerMode) {
    clearDirectStatusReset()
    setMode(nextMode)
    setComposerStatus(defaultComposerStatus(nextMode))
  }

  function selectAgent(agent: AgentSummary) {
    clearDirectStatusReset()
    setSelectedId(agent.id)
    setAgents((current) =>
      current.map((candidate) => (candidate.id === agent.id && candidate.unread > 0 ? { ...candidate, unread: 0 } : candidate)),
    )
  }

  const updateVisibleAgents = useCallback((nextVisibleAgents: AgentSummary[], filterActive: boolean) => {
    setVisibleAgents(nextVisibleAgents)
    setAgentFilterActive(filterActive)
  }, [])

  const moveSelection = useCallback(
    (delta: 1 | -1) => {
      const navigationAgents = agentFilterActive ? visibleAgents : agents
      if (navigationAgents.length === 0) return
      const currentIndex = navigationAgents.findIndex((agent) => agent.id === selectedIdRef.current)
      const fallbackIndex = delta > 0 ? 0 : navigationAgents.length - 1
      const nextIndex = currentIndex === -1 ? fallbackIndex : (currentIndex + delta + navigationAgents.length) % navigationAgents.length
      selectAgent(navigationAgents[nextIndex])
    },
    [agentFilterActive, agents, visibleAgents],
  )

  // Global keyboard shortcut listener
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const activeEl = document.activeElement
      const inField = activeEl && ['INPUT', 'TEXTAREA'].includes(activeEl.tagName)

      // 1. Cmd+K / Ctrl+K (Command Palette)
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((open) => !open)
        return
      }

      // 2. Escape to close overlays
      if (event.key === 'Escape') {
        setPaletteOpen(false)
        setShortcutsOpen(false)
        if (inField) (activeEl as HTMLElement).blur()
        return
      }

      // Don't intercept keyboard shortcuts when typing in inputs
      if (inField) return

      // 3. "?" to toggle Shortcuts panel
      if (event.key === '?') {
        event.preventDefault()
        setShortcutsOpen((open) => !open)
        return
      }

      // 4. "[" and "]" to navigate next/prev agent channel
      if (event.key === '[') {
        event.preventDefault()
        moveSelection(-1)
        return
      }
      if (event.key === ']') {
        event.preventDefault()
        moveSelection(1)
        return
      }

      // 5. "r" or "/" to focus composer input
      if (event.key === 'r' || event.key === '/') {
        event.preventDefault()
        const input = document.querySelector('.composer-input') as HTMLInputElement | HTMLTextAreaElement | null
        input?.focus()
        return
      }

      // 6. Legacy Ctrl-N / Ctrl-P selection navigation
      if (event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
        const key = event.key.toLowerCase()
        if (key === 'n' || key === 'p') {
          event.preventDefault()
          moveSelection(key === 'n' ? 1 : -1)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [moveSelection])

  async function submit(body: string) {
    if (!selectedAgent) return
    if (mode !== 'message') {
      setMode('message')
      setComposerStatus('Direct pane control is locked; reset to Message mode.')
      return
    }
    const target = targetForAgent(selectedAgent)
    const pending = optimisticMessage(selectedAgent.conversationKey, body)
    setMessages((current) => [...current, pending])
    setComposerStatus(status?.mode === 'tracker' ? 'Sending tracker message…' : 'Sending mock message…')

    const result = await runtime.sendMessage(target, body)
    if (result.ok && result.message) {
      window.setTimeout(() => {
        setMessages((current) =>
          current.map((message) => (message.id === pending.id ? { ...result.message!, deliveryState: 'delivered' } : message)),
        )
        setComposerStatus(status?.mode === 'tracker' ? 'Tracker message delivered.' : 'Mock message delivered.')
      }, 650)
    } else {
      setMessages((current) =>
        current.map((message) =>
          message.id === pending.id ? { ...message, deliveryState: 'failed', body: `${message.body}\n\n${result.error ?? 'Message failed.'}` } : message,
        ),
      )
      setComposerStatus(result.error ?? 'Message failed.')
    }
  }

  const details = selectedAgent ? (
    <>
      <dl className="detail-list">
        <div className="detail-row">
          <dt className="detail-key">Scope</dt>
          <dd className="detail-val">{selectedAgent.scope}</dd>
        </div>
        <div className="detail-row">
          <dt className="detail-key">Status</dt>
          <dd className="detail-val">{selectedAgent.status}</dd>
        </div>
        <div className="detail-row">
          <dt className="detail-key">Unread</dt>
          <dd className="detail-val">{selectedAgent.unread}</dd>
        </div>
        <div className="detail-row">
          <dt className="detail-key">Address</dt>
          <dd className="detail-val">
            <code>{selectedAgent.address}</code>
          </dd>
        </div>
        <div className="detail-row">
          <dt className="detail-key">CWD</dt>
          <dd className="detail-val">
            <code>{selectedAgent.cwd}</code>
          </dd>
        </div>
        <div className="detail-row">
          <dt className="detail-key">Tags</dt>
          <dd className="detail-val">{selectedAgent.tags.join(', ')}</dd>
        </div>
        <div className="detail-row">
          <dt className="detail-key">Direct control</dt>
          <dd className="detail-val">Locked / not implemented</dd>
        </div>
      </dl>



      <div className="info-note">
        <strong>Direct Text</strong> and <strong>Direct Keys</strong> remain locked in this tracker-focused UI.
      </div>

      <div className="info-card">
        <div className="info-card-title">{status?.mode === 'tracker' ? 'Tracker Simple View' : 'Mock boundary'}</div>
        <ul>
          {status?.mode === 'tracker' ? (
            <>
              <li>Local agent-tracker socket only</li>
              <li>Send/receive normal messages for local agents</li>
              <li>No registry, remote agents, or direct pane control</li>
              <li>Reply inbox identity is configured by environment</li>
            </>
          ) : (
            <>
              <li>Local fixture data only</li>
              <li>No tracker or registry calls</li>
              <li>No tmux pane control</li>
              <li>No persistence beyond this mock session</li>
            </>
          )}
        </ul>
      </div>
    </>
  ) : null

  return (
    <AppShell
      status={status}
      detailsOpen={detailsOpen}
      onCloseDetails={() => setDetailsOpen(false)}
      shortcutsOpen={shortcutsOpen}
      onOpenShortcuts={() => setShortcutsOpen(true)}
      onCloseShortcuts={() => setShortcutsOpen(false)}
      paletteOpen={paletteOpen}
      onOpenPalette={() => setPaletteOpen(true)}
      onClosePalette={() => setPaletteOpen(false)}
      agentsRaw={agents}
      onSelectAgent={selectAgent}
      agents={<AgentList agents={agents} selectedId={selectedId} onSelect={selectAgent} onVisibleAgentsChange={updateVisibleAgents} />}
      main={
        loading ? (
          <EmptyState />
        ) : selectedAgent ? (
          <div className="conversation-shell">
            <ConversationView
              agent={selectedAgent}
              messages={messages}
              detailsOpen={detailsOpen}
              onToggleDetails={() => setDetailsOpen((open) => !open)}
            />
            <Composer agent={selectedAgent} mode={mode} status={composerStatus} onModeChange={updateMode} onSubmit={submit} />
          </div>
        ) : (
          <EmptyState />
        )
      }
      details={details}
    />
  )
}
