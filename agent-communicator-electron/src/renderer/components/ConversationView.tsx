import { useEffect, useRef } from 'react'
import type { AgentSummary, Message } from '../../shared/contracts'
import { sortMessages } from '../features/conversations/conversationStore'
import { MessageBubble } from './MessageBubble'

interface Props {
  agent: AgentSummary
  messages: Message[]
  detailsOpen: boolean
  onToggleDetails: () => void
}

function initials(name: string): string {
  const parts = name.split(/[-_\s]+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

export function ConversationView({ agent, messages, detailsOpen, onToggleDetails }: Props) {
  const sortedMessages = sortMessages(messages)
  const timelineRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timeline = timelineRef.current
    if (timeline) timeline.scrollTop = timeline.scrollHeight
  }, [agent.conversationKey, sortedMessages.length])

  return (
    <>
      <div className="conv-head">
        <div className="conv-head-left">
          <div className="conv-head-avatar">{initials(agent.displayName)}</div>
          <div className="conv-head-text">
            <h1>{agent.displayName}</h1>
            <div className="conv-meta">
              <span className="conv-meta-status">
                <span className={`status-dot ${agent.status}`} /> {agent.status}
              </span>
              <span className="meta-sep">·</span>
              <span>{agent.project}</span>
              <span className="meta-sep">·</span>
              <span className="mono">{agent.address}</span>
            </div>
          </div>
        </div>
        <div className="conv-actions">
          <button className="btn">Mark read</button>
          <button className={`btn icon-only toggle-details ${detailsOpen ? 'active' : ''}`} title="Toggle agent details" onClick={onToggleDetails}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <rect x="2" y="3" width="12" height="10" rx="1.5" />
              <line x1="10" y1="3" x2="10" y2="13" />
            </svg>
          </button>
        </div>
      </div>

      <div className="conv-scroll" ref={timelineRef}>
        {sortedMessages.length === 0 ? (
          <div className="empty-card timeline-empty">No messages yet. Use the composer to send a normal inbox message.</div>
        ) : (
          sortedMessages.map((message) => <MessageBubble key={message.id} message={message} />)
        )}
      </div>
    </>
  )
}
