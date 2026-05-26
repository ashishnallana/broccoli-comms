import { ReactNode, useEffect, useRef, useState } from 'react'
import type { AgentSummary, Message } from '../../shared/contracts'
import { sortMessages } from '../features/conversations/conversationStore'
import { MessageBubble } from './MessageBubble'

interface Props {
  agent: AgentSummary
  messages: Message[]
  detailsOpen: boolean
  onToggleDetails: () => void
  onCapturePane: () => void
}

function initials(name: string): string {
  const parts = name.split(/[-_\s]+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

function isSameDay(date1Str: string, date2Str: string): boolean {
  const d1 = new Date(date1Str)
  const d2 = new Date(date2Str)
  return (
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate()
  )
}

function formatDateLabel(dateStr: string): string {
  const date = new Date(dateStr)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)

  if (date.toDateString() === today.toDateString()) return 'Today'
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'

  return date.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
}

export function ConversationView({ agent, messages, detailsOpen, onToggleDetails, onCapturePane }: Props) {
  const sortedMessages = sortMessages(messages)
  const timelineRef = useRef<HTMLDivElement>(null)
  const [focusedId, setFocusedId] = useState<string | undefined>()

  useEffect(() => {
    const timeline = timelineRef.current
    if (timeline) timeline.scrollTop = timeline.scrollHeight
  }, [agent.conversationKey, sortedMessages.length])

  // Set initial focused message to last message
  useEffect(() => {
    if (sortedMessages.length > 0) {
      setFocusedId(sortedMessages[sortedMessages.length - 1].id)
    } else {
      setFocusedId(undefined)
    }
  }, [sortedMessages.length, agent.conversationKey])

  // Keyboard handler for j/k navigation
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const activeEl = document.activeElement
      const inField = activeEl && ['INPUT', 'TEXTAREA'].includes(activeEl.tagName)
      if (inField) return

      if (e.key === 'j') {
        e.preventDefault()
        const currentIdx = sortedMessages.findIndex((m) => m.id === focusedId)
        const nextIdx = currentIdx === -1 ? 0 : Math.min(sortedMessages.length - 1, currentIdx + 1)
        const nextMsg = sortedMessages[nextIdx]
        if (nextMsg) {
          setFocusedId(nextMsg.id)
          setTimeout(() => {
            const el = document.querySelector('.msg-row.focused')
            el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
          }, 10)
        }
      } else if (e.key === 'k') {
        e.preventDefault()
        const currentIdx = sortedMessages.findIndex((m) => m.id === focusedId)
        const prevIdx = currentIdx === -1 ? sortedMessages.length - 1 : Math.max(0, currentIdx - 1)
        const prevMsg = sortedMessages[prevIdx]
        if (prevMsg) {
          setFocusedId(prevMsg.id)
          setTimeout(() => {
            const el = document.querySelector('.msg-row.focused')
            el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
          }, 10)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [focusedId, sortedMessages])

  const renderedElements: ReactNode[] = []
  let lastMessage: Message | null = null

  sortedMessages.forEach((message) => {
    // 1. Day separator
    if (!lastMessage || !isSameDay(lastMessage.createdAt, message.createdAt)) {
      renderedElements.push(
        <div key={`sep-${message.id}`} className="day-sep">
          {formatDateLabel(message.createdAt)}
        </div>
      )
    }

    // 2. Grouping logic (consecutive from same author within 5 minutes)
    let grouped = false
    if (lastMessage) {
      const timeDiff = new Date(message.createdAt).getTime() - new Date(lastMessage.createdAt).getTime()
      const sameAuthor = lastMessage.author === message.author
      const sameDirection = lastMessage.direction === message.direction
      if (sameAuthor && sameDirection && timeDiff < 5 * 60 * 1000) {
        grouped = true
      }
    }

    const isFocused = focusedId === message.id

    renderedElements.push(
      <MessageBubble
        key={message.id}
        message={message}
        grouped={grouped}
        focused={isFocused}
        onFocus={() => setFocusedId(message.id)}
      />
    )

    lastMessage = message
  })

  return (
    <>
      <div className="chan-head">
        <div className="chan-head-title">
          <span className="channel-sigil">#</span>
          <span>{agent.displayName}</span>
        </div>
        <div className="chan-head-divider"></div>
        <div className="chan-head-desc">
          live monitoring · {agent.project || agent.scope} · {agent.cwd || agent.address}
        </div>
        <div className="chan-head-spacer"></div>
        <div className="chan-head-actions">
          <button
            className="icon-btn"
            title="Capture Pane (Ctrl+X)"
            onClick={onCapturePane}
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M2 5h3l1.5-2h3L11 5h3v9H2V5z" strokeLinejoin="round" />
              <circle cx="8" cy="9.5" r="2.5" />
            </svg>
          </button>
          <button
            className={`icon-btn toggle-details ${detailsOpen ? 'active' : ''}`}
            title="Toggle agent details"
            onClick={onToggleDetails}
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <rect x="2" y="3" width="12" height="10" rx="1.5" />
              <line x1="10" y1="3" x2="10" y2="13" />
            </svg>
          </button>
        </div>
      </div>

      <div className={`feed ${agent.id.startsWith('group:') || agent.id.startsWith('host:') ? 'group-chat' : ''}`} id="feed" ref={timelineRef}>
        {renderedElements.length === 0 ? (
          <div className="empty-card">No messages yet. Use the composer below to send a message.</div>
        ) : (
          renderedElements
        )}
      </div>
    </>
  )
}
