import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { AgentSummary, ComposerMode, Message, RuntimeStatus, SavedAgent } from '../shared/contracts'
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
  const [securityWarning, setSecurityWarning] = useState<string | null>(null)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [visibleAgents, setVisibleAgents] = useState<AgentSummary[]>([])
  const [agentFilterActive, setAgentFilterActive] = useState(false)

  // Modal & overlay visibility states
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [launchModalOpen, setLaunchModalOpen] = useState(false)
  const [savedAgents, setSavedAgents] = useState<SavedAgent[]>([])

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
    setSecurityWarning(null)
  }, [selectedId])

  useEffect(() => {
    return () => clearDirectStatusReset()
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      const [runtimeStatus, agentList, savedList] = await Promise.all([
        runtime.getStatus(),
        runtime.listAgents(),
        runtime.listSavedAgents(),
      ])
      if (cancelled) return
      
      // Inject client-side Mock Group Channel
      const injectedGroupChannel: AgentSummary = {
        id: 'group:dev-team',
        name: 'dev-team',
        displayName: 'Dev Team Channel (#dev-team)',
        scope: 'local',
        status: 'idle',
        cwd: '/work/dev-team',
        project: 'Group Channel',
        address: '#dev-team',
        unread: 0,
        lastActiveAt: new Date().toISOString(),
        conversationKey: 'group:dev-team',
        canDirectControl: false,
        tags: ['group', 'local'],
      }
      
      const mergedAgents = [injectedGroupChannel, ...agentList]
      
      setStatus(runtimeStatus)
      setAgents(mergedAgents)
      setSelectedId(mergedAgents[0]?.id)
      setSavedAgents(savedList)
      setLoading(false)
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [runtime])

  // Client-side chronological group timeline aggregator
  const compileGroupTimeline = useCallback((groupMessagesMap: Record<string, Message[]>, memberIds: string[]): Message[] => {
    const allMsgs: Message[] = []
    const seenIds = new Set<string>()
    
    for (const memberId of memberIds) {
      const msgs = groupMessagesMap[memberId] || []
      for (const m of msgs) {
        if (!seenIds.has(m.id)) {
          seenIds.add(m.id)
          allMsgs.push(m)
        }
      }
    }
    
    // Sort chronologically
    return allMsgs.sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id))
  }, [])

  const reloadActiveMessages = useCallback(async () => {
    if (!selectedId) {
      setMessages([])
      return
    }
    const currentAgent = agents.find((a) => a.id === selectedId)
    if (!currentAgent) return

    if (currentAgent.id.startsWith('group:')) {
      const memberIds = agents.filter((a) => a.id !== currentAgent.id).map((a) => a.id)
      const messagesMap: Record<string, Message[]> = {}
      await Promise.all(
        memberIds.map(async (memberId) => {
          const activeMember = agents.find((a) => a.id === memberId)
          if (activeMember) {
            messagesMap[memberId] = await runtime.listMessages(activeMember.conversationKey)
          }
        })
      )
      const aggregated = compileGroupTimeline(messagesMap, memberIds)
      setMessages(aggregated)
    } else {
      const nextMessages = await runtime.listMessages(currentAgent.conversationKey)
      setMessages(nextMessages)
    }
  }, [runtime, selectedId, agents, compileGroupTimeline])

  // Watchlist Synchronizer: automatically update daemon watchlist on active channel change
  useEffect(() => {
    if (!selectedAgent) return
    let watchlist: string[] = []
    if (selectedAgent.id.startsWith('group:')) {
      watchlist = agents.filter((a) => a.id !== selectedAgent.id).map((a) => {
        return a.id.startsWith('local:') ? a.id.slice('local:'.length) : a.id
      })
    } else {
      const stableId = selectedAgent.id.startsWith('local:')
        ? selectedAgent.id.slice('local:'.length)
        : selectedAgent.id.startsWith('remote:')
        ? selectedAgent.id.slice('remote:'.length)
        : selectedAgent.id
      watchlist = [stableId]
    }
    runtime.updateWatchlist(watchlist)
  }, [selectedAgent, agents, runtime])

  // Trigger initial messages load and sync on active selectedAgent changes
  useEffect(() => {
    void reloadActiveMessages()
  }, [reloadActiveMessages])

  // Pushed Events Handler: listen for new messages and directory registration updates
  useEffect(() => {
    if (status?.mode !== 'tracker') return

    const unsubscribe = window.broccoliCommsMock?.onTrackerEvents(async (events) => {
      const hasMessages = events.some((e) => e.event_type === 'message_delivered' || e.event_type === 'remote_agent_event')
      const hasAgents = events.some((e) => e.event_type === 'agent_registered' || e.event_type === 'agent_unregistered')

      if (hasAgents) {
        const nextAgents = await runtime.listAgents()
        const injectedGroupChannel: AgentSummary = {
          id: 'group:dev-team',
          name: 'dev-team',
          displayName: 'Dev Team Channel (#dev-team)',
          scope: 'local',
          status: 'idle',
          cwd: '/work/dev-team',
          project: 'Group Channel',
          address: '#dev-team',
          unread: 0,
          lastActiveAt: new Date().toISOString(),
          conversationKey: 'group:dev-team',
          canDirectControl: false,
          tags: ['group', 'local'],
        }
        setAgents([injectedGroupChannel, ...nextAgents])
      }
      if (hasMessages) {
        void reloadActiveMessages()
      }
    })

    return () => {
      if (unsubscribe) unsubscribe()
    }
  }, [runtime, status, reloadActiveMessages])

  // Tracker Reset Handler: handle cursor expired notifications gracefully from the daemon
  useEffect(() => {
    if (status?.mode !== 'tracker') return

    const unsubscribeReset = window.broccoliCommsMock?.onTrackerResetRequired(async () => {
      const nextAgents = await runtime.listAgents()
      const injectedGroupChannel: AgentSummary = {
        id: 'group:dev-team',
        name: 'dev-team',
        displayName: 'Dev Team Channel (#dev-team)',
        scope: 'local',
        status: 'idle',
        cwd: '/work/dev-team',
        project: 'Group Channel',
        address: '#dev-team',
        unread: 0,
        lastActiveAt: new Date().toISOString(),
        conversationKey: 'group:dev-team',
        canDirectControl: false,
        tags: ['group', 'local'],
      }
      setAgents([injectedGroupChannel, ...nextAgents])
      void reloadActiveMessages()
    })

    return () => {
      if (unsubscribeReset) unsubscribeReset()
    }
  }, [runtime, status, reloadActiveMessages])

  useEffect(() => {
    if (status?.mode !== 'tracker') return

    const unsubscribeDenied = window.broccoliCommsMock?.onTrackerWatchDenied((errorMsg) => {
      setSecurityWarning(errorMsg)
    })

    return () => {
      if (unsubscribeDenied) unsubscribeDenied()
    }
  }, [status])



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

      // 3. Legacy Ctrl-N / Ctrl-P & Ctrl-X selection / capture triggers (Bypass input focus checks)
      if (event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
        const key = event.key.toLowerCase()
        if (key === 'n' || key === 'p') {
          event.preventDefault()
          moveSelection(key === 'n' ? 1 : -1)
          return
        }
        if (key === 'x') {
          event.preventDefault()
          capturePane()
          return
        }
      }

      // Don't intercept keyboard shortcuts when typing in inputs
      if (inField) return

      // 4. "?" to toggle Shortcuts panel
      if (event.key === '?') {
        event.preventDefault()
        setShortcutsOpen((open) => !open)
        return
      }

      // 5. "[" and "]" to navigate next/prev agent channel
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

      // 6. "r" or "/" to focus composer input
      if (event.key === 'r' || event.key === '/') {
        event.preventDefault()
        const input = document.querySelector('.composer-input') as HTMLInputElement | HTMLTextAreaElement | null
        input?.focus()
        return
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [moveSelection, selectedAgent, status])

  async function launchAgent(configName: string, directory: string) {
    setComposerStatus(`Spinning agent ${configName} in Tmux...`)
    const result = await runtime.spinAgent(configName, directory)
    if (result.ok) {
      setComposerStatus(result.summary || `Agent ${configName} spun successfully!`)
      const agentList = await runtime.listAgents()
      setAgents(agentList)
    } else {
      setComposerStatus(result.error ?? 'Failed to spin agent.')
    }
    return result
  }

  async function browseDirectory() {
    return runtime.selectLocalDirectory()
  }

  async function capturePane() {
    if (!selectedAgent) return
    setComposerStatus(`Capturing pane snapshot for ${selectedAgent.displayName}...`)
    const result = await runtime.sendPaneCapture(
      selectedAgent.conversationKey,
      status?.mode === 'tracker' ? 'agent-communicator' : selectedAgent.conversationKey,
    )
    if (result.ok) {
      setComposerStatus(result.summary || `Pane snapshot for ${selectedAgent.displayName} delivered successfully!`)
      const nextMessages = await runtime.listMessages(selectedAgent.conversationKey)
      setMessages(nextMessages)
    } else {
      setComposerStatus(result.error ?? 'Failed to capture pane.')
    }
  }

  async function submit(body: string) {
    if (!selectedAgent) return
    const target = targetForAgent(selectedAgent)

    if (mode === 'directText') {
      setComposerStatus(`Injecting direct text into ${selectedAgent.displayName}...`)
      const result = await runtime.sendDirectText(target, body, true)
      if (result.ok) {
        setComposerStatus(`Direct text successfully injected!`)
        resetComposerStatusAfterDelay()
      } else {
        setComposerStatus(result.error ?? 'Failed to inject direct text.')
      }
      return
    }

    if (mode === 'directKeys') {
      try {
        const payload = JSON.parse(body)
        if (payload.type === 'keys') {
          setComposerStatus(`Injecting key strokes [${payload.keys.join(', ')}] into ${selectedAgent.displayName}...`)
          const result = await runtime.sendDirectKeys(target, payload.keys)
          if (result.ok) {
            setComposerStatus(`Keys successfully injected!`)
            resetComposerStatusAfterDelay()
          } else {
            setComposerStatus(result.error ?? 'Failed to inject keys.')
          }
          return
        }
      } catch {
        const keys = body.split(/[\s,]+/).filter(Boolean)
        setComposerStatus(`Injecting key strokes [${keys.join(', ')}] into ${selectedAgent.displayName}...`)
        const result = await runtime.sendDirectKeys(target, keys)
        if (result.ok) {
          setComposerStatus(`Keys successfully injected!`)
          resetComposerStatusAfterDelay()
        } else {
          setComposerStatus(result.error ?? 'Failed to inject keys.')
        }
        return
      }
    }

    // Message mode
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

  function resetComposerStatusAfterDelay() {
    if (directStatusResetTimer.current !== undefined) {
      window.clearTimeout(directStatusResetTimer.current)
    }
    directStatusResetTimer.current = window.setTimeout(() => {
      setComposerStatus(defaultComposerStatus(modeRef.current))
    }, 2500) as any
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
          <dd className="detail-val" style={{ color: 'var(--accent-emerald)', fontWeight: 700 }}>Unlocked / Operational</dd>
        </div>
      </dl>

      <div className="info-note">
        <strong>Direct Control Unlocked!</strong> Switch composer tab modes to <strong>Direct Text</strong> or <strong>Direct Keys</strong> to inject command text and custom Unix keystrokes.
      </div>

      {securityWarning && (
        <div className="info-note warning" style={{ borderLeftColor: 'var(--accent-red)', background: 'rgba(239, 68, 68, 0.06)' }}>
          <strong style={{ color: 'var(--accent-red)' }}>Observation Scope Degraded:</strong> {securityWarning}
          <div style={{ fontSize: '11px', marginTop: '4px', opacity: 0.8 }}>
            Broad passive remote DMs are denied. Gracefully fell back to narrow requester-visible local timelines.
          </div>
        </div>
      )}

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
      launchModalOpen={launchModalOpen}
      onCloseLaunchModal={() => setLaunchModalOpen(false)}
      onLaunchAgent={launchAgent}
      onBrowseDirectory={browseDirectory}
      savedAgents={savedAgents}
      agents={
        <AgentList
          agents={agents}
          selectedId={selectedId}
          onSelect={selectAgent}
          onVisibleAgentsChange={updateVisibleAgents}
          onOpenLaunch={() => setLaunchModalOpen(true)}
        />
      }
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
              onCapturePane={capturePane}
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
