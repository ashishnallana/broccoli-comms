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

export interface GroupChannel {
  id: string
  name: string
  memberIds: string[]
  isHostGroup?: boolean
}

const DEFAULT_GROUPS: Record<string, GroupChannel> = {
  'group:dev-team': {
    id: 'group:dev-team',
    name: 'dev-team',
    memberIds: []
  }
}

const parseHostname = (agent: AgentSummary): string => {
  if (agent.scope === 'local') return 'local-host'
  let addr = agent.address || agent.name
  if (addr.startsWith('registry:')) {
    addr = addr.slice('registry:'.length)
  }
  if (addr.includes('/')) {
    return addr.split('/')[0]
  }
  return 'unknown-host'
}

function initials(name: string): string {
  const parts = name.split(/[-_\s]+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

function statusDotClass(status: string): string {
  if (status === 'offline') return 'error'
  if (status === 'waiting' || status === 'busy') return 'warn'
  if (status === 'idle') return ''
  return 'idle'
}

export function avatarBg(name: string): string {
  const colors = [
    'var(--accent-blue)',
    'var(--accent-purple)',
    'var(--accent-pink)',
    'var(--accent-amber)',
    'var(--accent-emerald)',
    'var(--accent-teal)',
  ]
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  const index = Math.abs(hash) % colors.length
  return colors[index]
}

export function App() {
  const runtime = useMemo(() => createRuntimeClient(), [])
  const [status, setStatus] = useState<RuntimeStatus | null>(null)
  const [rawAgents, setRawAgents] = useState<AgentSummary[]>([])
  const [selectedId, setSelectedId] = useState<string>()
  const [messages, setMessages] = useState<Message[]>([])
  const [mode, setMode] = useState<ComposerMode>('message')
  const [composerStatus, setComposerStatus] = useState(defaultComposerStatus('message'))
  const [loading, setLoading] = useState(true)
  const [securityWarning, setSecurityWarning] = useState<string | null>(null)
  const [groups, setGroups] = useState<Record<string, GroupChannel>>(() => {
    try {
      const stored = localStorage.getItem('agent-communicator-groups')
      if (stored) {
        const parsed = JSON.parse(stored)
        if (Object.keys(parsed).length > 0) return parsed
      }
    } catch {}
    return DEFAULT_GROUPS
  })
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean
    x: number
    y: number
    agentId: string
  } | null>(null)
  const [promptModal, setPromptModal] = useState<{
    isOpen: boolean
    title: string
    placeholder: string
    onSubmit: (value: string) => void
  } | null>(null)
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

  const hostnameGroups = useMemo<GroupChannel[]>(() => {
    const hosts: Record<string, string[]> = {}
    for (const a of rawAgents) {
      const host = parseHostname(a)
      if (host === 'unknown-host') continue
      if (!hosts[host]) {
        hosts[host] = []
      }
      hosts[host].push(a.id)
    }

    return Object.entries(hosts)
      .filter(([_, memberIds]) => memberIds.length > 0)
      .map(([host, memberIds]) => ({
        id: `host:${host}`,
        name: `${host} (host)`,
        memberIds,
        isHostGroup: true
      }))
  }, [rawAgents])

  const allGroups = useMemo<GroupChannel[]>(() => {
    const customList = Object.values(groups)
    return [...hostnameGroups, ...customList]
  }, [hostnameGroups, groups])

  // Map GroupChannel records into React sidebar AgentSummary items
  const groupToAgentSummary = useCallback((group: GroupChannel): AgentSummary => {
    const displayName = group.isHostGroup ? `Host: #${group.name}` : `Group: #${group.name}`
    return {
      id: group.id,
      name: group.name,
      displayName,
      scope: 'local',
      status: 'idle',
      cwd: `/work/groups/${group.name}`,
      project: 'Group Channel',
      address: `#${group.name}`,
      unread: 0,
      lastActiveAt: new Date().toISOString(),
      conversationKey: group.id,
      canDirectControl: false,
      tags: ['group', 'local'],
    }
  }, [])

  const mailboxChannel = useMemo<AgentSummary>(() => {
    const mailboxName = 'agent-communicator'
    return {
      id: `mailbox:${mailboxName}`,
      name: mailboxName,
      displayName: `Inbox: ${mailboxName} (mailbox)`,
      scope: 'local',
      status: 'idle',
      cwd: '/work/mailbox',
      project: 'Mailbox Channel',
      address: `@${mailboxName}`,
      unread: 0,
      lastActiveAt: new Date().toISOString(),
      conversationKey: `mailbox:${mailboxName}`,
      canDirectControl: false,
      tags: ['mailbox', 'inbox', 'local'],
    }
  }, [])

  const agents = useMemo<AgentSummary[]>(() => {
    const groupSummaries = allGroups.map(groupToAgentSummary)
    return [mailboxChannel, ...groupSummaries, ...rawAgents]
  }, [mailboxChannel, allGroups, rawAgents, groupToAgentSummary])

  const selectedAgent = agents.find((agent) => agent.id === selectedId)

  useEffect(() => {
    if (agents.length > 0 && !selectedId) {
      setSelectedId(agents[0].id)
    }
  }, [agents, selectedId])

  useEffect(() => {
    let cancelled = false
    async function load() {
      const [runtimeStatus, agentList, savedList] = await Promise.all([
        runtime.getStatus(),
        runtime.listAgents(),
        runtime.listSavedAgents(),
      ])
      if (cancelled) return
      
      setStatus(runtimeStatus)
      setRawAgents(agentList)
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

  const getGroupMembers = useCallback((groupId: string): string[] => {
    if (groupId.startsWith('host:')) {
      return hostnameGroups.find((hg) => hg.id === groupId)?.memberIds || []
    }
    const group = groups[groupId]
    if (!group) return []
    if (groupId === 'group:dev-team' && group.memberIds.length === 0) {
      return agents.filter((a) => a.id !== groupId && !a.id.startsWith('group:') && !a.id.startsWith('host:') && a.scope === 'local').map((a) => a.id)
    }
    return group.memberIds
  }, [groups, hostnameGroups, agents])

  const createGroup = useCallback((name: string) => {
    const cleanName = name.trim().replace(/[^A-Za-z0-9_-]/g, '_')
    if (!cleanName) return
    const gId = `group:${cleanName}`
    setGroups((current) => {
      if (current[gId]) return current
      return {
        ...current,
        [gId]: {
          id: gId,
          name: cleanName,
          memberIds: []
        }
      }
    })
  }, [])

  const addAgentToGroup = useCallback((agentId: string, groupId: string) => {
    setGroups((current) => {
      const group = current[groupId]
      if (!group) return current
      if (group.memberIds.includes(agentId)) return current
      return {
        ...current,
        [groupId]: {
          ...group,
          memberIds: [...group.memberIds, agentId]
        }
      }
    })
  }, [])

  const removeAgentFromGroup = useCallback((agentId: string, groupId: string) => {
    setGroups((current) => {
      const group = current[groupId]
      if (!group) return current
      return {
        ...current,
        [groupId]: {
          ...group,
          memberIds: group.memberIds.filter((id) => id !== agentId)
        }
      }
    })
  }, [])

  // Persist groups to localStorage on membership changes
  useEffect(() => {
    localStorage.setItem('agent-communicator-groups', JSON.stringify(groups))
  }, [groups])

  // Global click listener to dismiss custom context menu on clicks
  useEffect(() => {
    const handleGlobalClick = () => {
      setContextMenu(null)
    }
    window.addEventListener('click', handleGlobalClick)
    return () => window.removeEventListener('click', handleGlobalClick)
  }, [])

  const reloadActiveMessages = useCallback(async () => {
    if (!selectedId) {
      setMessages([])
      return
    }
    const currentAgent = agents.find((a) => a.id === selectedId)
    if (!currentAgent) return

    if (currentAgent.id.startsWith('group:') || currentAgent.id.startsWith('host:')) {
      try {
        const nextMessages = await runtime.listGroupMessages(currentAgent.id)
        setMessages(nextMessages)
      } catch (e) {
        console.warn('listGroupMessages failed, falling back to manual per-member inbox aggregation:', e)
        const memberIds = getGroupMembers(currentAgent.id)
        const messagesMap: Record<string, Message[]> = {}
        await Promise.all(
          memberIds.map(async (memberId) => {
            const activeMember = agents.find((a) => a.id === memberId)
            if (activeMember) {
              messagesMap[memberId] = await runtime.listMessages(activeMember.conversationKey, activeMember.name)
            }
          })
        )
        const aggregated = compileGroupTimeline(messagesMap, memberIds)
        setMessages(aggregated)
      }
    } else {
      const nextMessages = await runtime.listMessages(currentAgent.conversationKey)
      setMessages(nextMessages)
    }
  }, [runtime, selectedId, agents, compileGroupTimeline, getGroupMembers])

  // Watchlist Synchronizer: automatically update daemon watchlist on active channel change
  useEffect(() => {
    if (!selectedAgent) return
    if (selectedAgent.id.startsWith('group:') || selectedAgent.id.startsWith('host:')) {
      const members = getGroupMembers(selectedAgent.id)
      runtime.updateWatchlist({
        mode: 'group',
        groupId: selectedAgent.id,
        members
      })
    } else if (selectedAgent.id.startsWith('mailbox:')) {
      runtime.updateWatchlist([])
    } else {
      const stableId = selectedAgent.id.startsWith('local:')
        ? selectedAgent.id.slice('local:'.length)
        : selectedAgent.id.startsWith('remote:')
        ? selectedAgent.id.slice('remote:'.length)
        : selectedAgent.id
      runtime.updateWatchlist([stableId])
    }
  }, [selectedAgent, agents, runtime, getGroupMembers])

  // Trigger initial messages load and sync on active selectedAgent changes
  useEffect(() => {
    void reloadActiveMessages()
  }, [reloadActiveMessages])

  // Pushed Events Handler: listen for new messages and directory registration updates
  useEffect(() => {
    if (status?.mode !== 'tracker') return

    const unsubscribe = window.broccoliCommsMock?.onTrackerEvents(async (events) => {
      const trackerEventType = (event: any) => event.event_type ?? event.type

      const hasMessages = events.some((event) => {
        const type = trackerEventType(event)
        return type === 'message_delivered' || type === 'remote_agent_event' || type === 'message_notified'
      })

      const hasAgents = events.some((event) => {
        const type = trackerEventType(event)
        return type === 'agent_registered' || type === 'agent_unregistered'
      })

      if (hasAgents) {
        const nextAgents = await runtime.listAgents()
        setRawAgents(nextAgents)
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
      setRawAgents(nextAgents)
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
    setRawAgents((current) =>
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
      setRawAgents(agentList)
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
      const isRemote = selectedAgent.scope === 'remote'
      if (isRemote) {
        setComposerStatus(`Remote pane capture requested; waiting for snapshot...`)
      } else {
        setComposerStatus(result.summary || `Pane snapshot for ${selectedAgent.displayName} delivered successfully!`)
        const nextMessages = await runtime.listMessages(selectedAgent.conversationKey)
        setMessages(nextMessages)
      }
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

  const selectedGroup = allGroups.find((g) => g.id === selectedId)

  const details = selectedGroup ? (
    <>
      <h4 style={{ fontSize: '12px', color: 'var(--text-light)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '12px' }}>
        Group Members ({getGroupMembers(selectedGroup.id).length})
      </h4>
      <div className="group-members-list">
        {getGroupMembers(selectedGroup.id).map((mId) => {
          const member = agents.find((a) => a.id === mId)
          if (!member) return null
          return (
            <button
              key={member.id}
              className="member-row"
              onClick={() => selectAgent(member)}
            >
              <span className="agent-avatar-sm" style={{ background: avatarBg(member.displayName) }}>
                {initials(member.displayName)}
              </span>
              <span style={{ flex: 1, fontSize: '12.5px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {member.displayName}
              </span>
              <span className={`channel-status-dot ${statusDotClass(member.status)}`} style={{ width: '6px', height: '6px', minWidth: '6px' }} />
            </button>
          )
        })}
      </div>

      {selectedGroup.isHostGroup && (
        <div className="info-note" style={{ marginTop: '16px' }}>
          <strong>Host Monitoring Timeline:</strong> This dynamic group automatically aggregates events for all agents running on the machine <code>{selectedGroup.name.replace(' (host)', '')}</code>.
        </div>
      )}
    </>
  ) : selectedAgent && selectedAgent.id.startsWith('mailbox:') ? (
    <>
      <dl className="detail-list">
        <div className="detail-row">
          <dt className="detail-key">Identity</dt>
          <dd className="detail-val"><code>{selectedAgent.name}</code></dd>
        </div>
        <div className="detail-row">
          <dt className="detail-key">Type</dt>
          <dd className="detail-val">Shared Mailbox</dd>
        </div>
        <div className="detail-row">
          <dt className="detail-key">CWD</dt>
          <dd className="detail-val"><code>/work/mailbox</code></dd>
        </div>
        <div className="detail-row">
          <dt className="detail-key">Observed Messages</dt>
          <dd className="detail-val" style={{ color: 'var(--accent-blue)', fontWeight: 700 }}>{messages.length} Messages</dd>
        </div>
        <div className="detail-row">
          <dt className="detail-key">Direct control</dt>
          <dd className="detail-val" style={{ color: 'var(--accent-rose)', fontWeight: 700 }}>Disabled (Inbox Only)</dd>
        </div>
      </dl>

      <div className="info-note">
        <strong>Global Mailbox View:</strong> This segment displays every fanned-out remote watchevents event and incoming DM message delivered to the shared <code>{selectedAgent.name}</code> inbox.
      </div>
    </>
  ) : selectedAgent ? (
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

  const handleAgentContextMenu = useCallback((e: React.MouseEvent, agentId: string) => {
    e.preventDefault()
    if (agentId.startsWith('group:') || agentId.startsWith('host:')) return
    setContextMenu({
      visible: true,
      x: e.clientX,
      y: e.clientY,
      agentId
    })
  }, [])

  const promptModalElement = promptModal && promptModal.isOpen ? (
    <div
      className="prompt-modal-overlay"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0, 0, 0, 0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999
      }}
      onClick={() => setPromptModal(null)}
    >
      <div
        className="prompt-modal-content"
        style={{
          background: 'var(--surface-card)',
          border: '1px solid var(--hairline)',
          borderRadius: 'var(--r-md)',
          padding: '20px',
          width: '360px',
          boxShadow: '0 12px 40px rgba(0,0,0,0.5)'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--on-dark)', marginBottom: '12px' }}>
          {promptModal.title}
        </div>
        <input
          id="prompt-modal-input"
          className="search-input"
          placeholder={promptModal.placeholder}
          style={{ width: '100%', margin: '0 0 16px 0' }}
          autoFocus
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              const val = (e.target as HTMLInputElement).value.trim()
              if (val) {
                promptModal.onSubmit(val)
                setPromptModal(null)
              }
            } else if (e.key === 'Escape') {
              setPromptModal(null)
            }
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button
            className="btn"
            style={{ height: '28px', padding: '0 12px', fontSize: '12px', cursor: 'pointer' }}
            onClick={() => setPromptModal(null)}
          >
            Cancel
          </button>
          <button
            className="btn primary"
            style={{ height: '28px', padding: '0 12px', fontSize: '12px', cursor: 'pointer' }}
            onClick={() => {
              const input = document.getElementById('prompt-modal-input') as HTMLInputElement
              const val = input?.value.trim()
              if (val) {
                promptModal.onSubmit(val)
                setPromptModal(null)
              }
            }}
          >
            Create
          </button>
        </div>
      </div>
    </div>
  ) : null

  const contextMenuElement = contextMenu ? (
    <div
      className="custom-context-menu"
      style={{
        position: 'absolute',
        top: `${contextMenu.y}px`,
        left: `${contextMenu.x}px`
      }}
    >
      <div className="menu-section-title">Add to group</div>
      {Object.entries(groups).map(([gId, group]) => {
        const alreadyMember = group.memberIds.includes(contextMenu.agentId)
        if (alreadyMember) return null
        return (
          <button
            key={gId}
            className="menu-item"
            onClick={(event) => {
              event.stopPropagation()
              addAgentToGroup(contextMenu.agentId, gId)
              setContextMenu(null)
            }}
          >
            + #{group.name}
          </button>
        )
      })}
      <button
        className="menu-item create"
        onClick={(event) => {
          event.stopPropagation()
          const targetAgentId = contextMenu.agentId
          setPromptModal({
            isOpen: true,
            title: 'Create New Group',
            placeholder: 'Enter group name (e.g. dev-team)',
            onSubmit: (name) => {
              const cleanName = name.trim().replace(/[^A-Za-z0-9_-]/g, '_')
              if (!cleanName) return
              const gId = `group:${cleanName}`
              setGroups((current) => ({
                ...current,
                [gId]: {
                  id: gId,
                  name: cleanName,
                  memberIds: [...new Set([...(current[gId]?.memberIds ?? []), targetAgentId])]
                }
              }))
            }
          })
          setContextMenu(null)
        }}
      >
        [+] Create New Group...
      </button>

      {Object.entries(groups).some(([_, g]) => g.memberIds.includes(contextMenu.agentId)) && (
        <>
          <div className="menu-section-title" style={{ borderTop: '1px solid var(--hairline)', marginTop: '4px' }}>Remove from group</div>
          {Object.entries(groups).map(([gId, group]) => {
            const isMember = group.memberIds.includes(contextMenu.agentId)
            if (!isMember) return null
            return (
              <button
                key={gId}
                className="menu-item destructive"
                onClick={(event) => {
                  event.stopPropagation()
                  removeAgentFromGroup(contextMenu.agentId, gId)
                  setContextMenu(null)
                }}
              >
                - #{group.name}
              </button>
            )
          })}
        </>
      )}
    </div>
  ) : null

  return (
    <>
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
            onOpenCreateGroup={() => {
              setPromptModal({
                isOpen: true,
                title: 'Create Custom Group Channel',
                placeholder: 'Enter group name (e.g. dev-team)',
                onSubmit: (name) => {
                  createGroup(name)
                }
              })
            }}
            onAgentContextMenu={handleAgentContextMenu}
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
              {selectedAgent.id.startsWith('group:') || selectedAgent.id.startsWith('host:') || selectedAgent.id.startsWith('mailbox:') ? (
                <div className="read-only-group-banner" style={{ padding: '16px 24px', background: 'var(--bg-surface)', borderTop: '1px solid var(--border-light)', color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center' }}>
                  {selectedAgent.id.startsWith('mailbox:')
                    ? `Inbox mailbox is read-only. Select a dynamic group or individual agent to compose private messages.`
                    : `Group channels are read-only. Select an individual agent card in the sidebar to send direct DMs or execute direct control input.`
                  }
                </div>
              ) : (
                <Composer agent={selectedAgent} mode={mode} status={composerStatus} onModeChange={updateMode} onSubmit={submit} />
              )}
            </div>
          ) : (
            <EmptyState />
          )
        }
        details={details}
      />
      {contextMenuElement}
      {promptModalElement}
    </>
  )
}
