import { useEffect, useMemo, useRef, useState } from 'react'
import type { AgentSummary, ComposerMode, Message, RuntimeStatus } from '../shared/contracts'
import { AgentList } from './components/AgentList'
import { AppShell } from './components/AppShell'
import { Composer } from './components/Composer'
import { ConversationView } from './components/ConversationView'
import { EmptyState } from './components/EmptyState'
import { Sidebar } from './components/Sidebar'
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
    async function loadMessages() {
      if (!selectedAgent) {
        setMessages([])
        return
      }
      const nextMessages = await runtime.listMessages(selectedAgent.conversationKey)
      if (!cancelled) setMessages(nextMessages)
    }
    void loadMessages()
    return () => {
      cancelled = true
    }
  }, [runtime, selectedAgent])

  useEffect(() => {
    if (selectedAgent && mode !== 'message' && !selectedAgent.canDirectControl) {
      setMode('message')
      setComposerStatus('Direct pane control is disabled for remote mock agents; reset to Message mode.')
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

  async function submit(body: string) {
    if (!selectedAgent) return
    if (mode !== 'message' && !selectedAgent.canDirectControl) {
      setMode('message')
      setComposerStatus('Direct pane control is disabled for remote mock agents; reset to Message mode.')
      return
    }
    const target = targetForAgent(selectedAgent)
    if (mode === 'message') {
      const pending = optimisticMessage(selectedAgent.conversationKey, body)
      setMessages((current) => [...current, pending])
      setComposerStatus('Sending mock message…')

      const result = await runtime.sendMessage(target, body)
      if (result.ok && result.message) {
        window.setTimeout(() => {
          setMessages((current) =>
            current.map((message) => (message.id === pending.id ? { ...result.message!, deliveryState: 'delivered' } : message)),
          )
          setComposerStatus('Mock message delivered.')
        }, 650)
      } else {
        setMessages((current) =>
          current.map((message) =>
            message.id === pending.id ? { ...message, deliveryState: 'failed', body: `${message.body}\n\n${result.error ?? 'Mock message failed.'}` } : message,
          ),
        )
        setComposerStatus(result.error ?? 'Mock message failed.')
      }
      return
    }

    const result =
      mode === 'directText'
        ? await runtime.sendDirectText(target, body, true)
        : await runtime.sendDirectKeys(target, body.split(/\s+/).filter(Boolean))
    clearDirectStatusReset()
    setComposerStatus(result.summary)
    const actionMode = mode
    const actionAgentId = selectedAgent.id
    directStatusResetTimer.current = window.setTimeout(() => {
      if (selectedIdRef.current === actionAgentId && modeRef.current === actionMode) {
        setComposerStatus(defaultComposerStatus(actionMode))
      }
      directStatusResetTimer.current = undefined
    }, 2600)
  }

  const details = selectedAgent ? (
    <div className="details-card">
      <h2>Agent details</h2>
      <dl>
        <dt>Scope</dt>
        <dd>{selectedAgent.scope}</dd>
        <dt>Status</dt>
        <dd>{selectedAgent.status}</dd>
        <dt>Unread</dt>
        <dd>{selectedAgent.unread}</dd>
        <dt>CWD</dt>
        <dd>{selectedAgent.cwd}</dd>
        <dt>Address</dt>
        <dd>{selectedAgent.address}</dd>
        <dt>Tags</dt>
        <dd>{selectedAgent.tags.join(', ')}</dd>
        <dt>Direct control</dt>
        <dd>{selectedAgent.canDirectControl ? 'Local mock enabled' : 'Disabled for remote mock agents'}</dd>
      </dl>
      <div className="warning-card">Direct Text and Direct Keys are explicit mock-only pane-control modes.</div>
      <div className="mock-boundary-card">
        <h3>Mock boundary</h3>
        <ul>
          <li>Local fixture data only</li>
          <li>No tracker or registry calls</li>
          <li>No tmux pane control</li>
          <li>No persistence beyond this mock session</li>
        </ul>
      </div>
    </div>
  ) : null

  return (
    <AppShell
      sidebar={<Sidebar status={status} />}
      agents={<AgentList agents={agents} selectedId={selectedId} onSelect={selectAgent} />}
      main={
        loading ? (
          <EmptyState />
        ) : selectedAgent ? (
          <div className="conversation-shell">
            <ConversationView agent={selectedAgent} messages={messages} />
            <Composer
              agent={selectedAgent}
              mode={mode}
              status={composerStatus}
              onModeChange={updateMode}
              onSubmit={submit}
            />
          </div>
        ) : (
          <EmptyState />
        )
      }
      details={details}
    />
  )
}
