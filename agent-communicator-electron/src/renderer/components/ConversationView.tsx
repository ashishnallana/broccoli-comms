import { useEffect, useRef } from 'react'
import type { AgentSummary, Message } from '../../shared/contracts'
import { sortMessages } from '../features/conversations/conversationStore'
import { MessageBubble } from './MessageBubble'

interface Props {
  agent: AgentSummary
  messages: Message[]
}

export function ConversationView({ agent, messages }: Props) {
  const sortedMessages = sortMessages(messages)
  const offline = agent.status === 'offline'
  const timelineRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timeline = timelineRef.current
    if (timeline) timeline.scrollTop = timeline.scrollHeight
  }, [agent.conversationKey, sortedMessages.length])

  return (
    <section className={`conversation-view ${offline ? 'with-offline-banner' : ''}`}>
      <header className="conversation-header">
        <div>
          <span className="eyebrow">{agent.scope} conversation</span>
          <h1>{agent.displayName}</h1>
          <p>
            <span className={`status-badge ${agent.status}`}>{agent.status}</span>
            <span>{agent.cwd}</span>
          </p>
        </div>
        <div className="header-actions">
          <button>Mark read</button>
          <button>Copy target</button>
          <button className="danger" disabled={!agent.canDirectControl}>
            Mock focus
          </button>
        </div>
      </header>
      {offline ? (
        <div className="offline-banner">
          <strong>Offline fixture state</strong>
          <span>This mock agent is unavailable; direct pane controls stay locked and messages remain local-only.</span>
        </div>
      ) : null}
      <div className="timeline" ref={timelineRef}>
        {sortedMessages.length === 0 ? (
          <div className="timeline-empty">
            <strong>No mock messages yet.</strong>
            <span>Use the composer to add a local outbound fixture message.</span>
          </div>
        ) : (
          sortedMessages.map((message) => <MessageBubble key={message.id} message={message} />)
        )}
      </div>
    </section>
  )
}
