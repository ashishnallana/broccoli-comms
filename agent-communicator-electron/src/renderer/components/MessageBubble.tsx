import type { ReactNode } from 'react'
import type { Message } from '../../shared/contracts'
import { formatTime } from '../lib/time'
import { avatarBg } from './AgentCard'

interface Props {
  message: Message
  grouped?: boolean
  focused?: boolean
  onFocus?: () => void
}

function initials(name: string): string {
  const parts = name.split(/[-_\s]+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

function inferKind(body: string): 'tool' | 'handoff' | 'commit' | 'error' | null {
  const lower = body.toLowerCase()
  if (lower.includes('tool ·') || lower.includes('tool:') || lower.includes('reading file') || lower.includes('executing') || lower.startsWith('tool ·')) return 'tool'
  if (lower.includes('handoff') || lower.includes('handing off')) return 'handoff'
  if (/^[0-9a-f]{7}\s*—/i.test(body) || lower.includes('files changed') || lower.includes('commit:')) return 'commit'
  if (lower.includes('failed') || lower.includes('error') || lower.includes('exception') || lower.startsWith('build failed')) return 'error'
  return null
}

function renderInlineCode(text: string): ReactNode {
  if (text.includes('`')) {
    const parts = text.split('`')
    return (
      <>
        {parts.map((part, idx) => {
          if (idx % 2 === 1) {
            return <code key={idx}>{part}</code>
          }
          return part
        })}
      </>
    )
  }
  return text
}

function renderBody(body: string): ReactNode {
  if (body.includes('```')) {
    const parts = body.split('```')
    return parts.map((part, idx) => {
      if (idx % 2 === 1) {
        const lines = part.trim().split('\n')
        const firstLine = lines[0].toLowerCase()
        const hasLang = ['javascript', 'typescript', 'json', 'bash', 'sh', 'nix', 'python', 'go'].includes(firstLine)
        const codeLines = hasLang ? lines.slice(1) : lines
        return (
          <pre key={idx}>
            {codeLines.join('\n')}
          </pre>
        )
      }
      return <span key={idx}>{renderInlineCode(part)}</span>
    })
  }
  return renderInlineCode(body)
}

export function MessageBubble({ message, grouped = false, focused = false, onFocus }: Props) {
  const displayAuthor = message.direction === 'outbound' ? 'you' : message.author
  const kind = inferKind(message.body)

  // Format time in HH:MM AM/PM
  const fullTimeStr = formatTime(message.createdAt)
  const timeParts = fullTimeStr.split(' ')
  const shortTime = timeParts[timeParts.length - 1] // e.g. "10:42" or similar depending on helper output format

  return (
    <div
      className={`msg-row ${grouped ? 'grouped' : ''} ${focused ? 'focused' : ''}`}
      tabIndex={0}
      onFocus={onFocus}
    >
      <div className="msg-gutter">
        {grouped ? (
          <span className="msg-time">{shortTime}</span>
        ) : (
          <div className="msg-avatar-wrap">
            <div className="msg-avatar" style={{ background: avatarBg(message.author) }}>
              {initials(displayAuthor)}
            </div>
          </div>
        )}
      </div>
      <div className="msg-content">
        {!grouped && (
          <div className="msg-author">
            <span className="msg-author-name">{displayAuthor}</span>
            <span className="msg-author-arrow">→</span>
            <span className="msg-author-recipient">
              {message.direction === 'outbound' ? `@${message.conversationKey}` : '#group'}
            </span>
            {kind && <span className={`msg-kind ${kind}`}>{kind}</span>}
            <span className="msg-author-time">{fullTimeStr}</span>
          </div>
        )}
        <div className="msg-body">{renderBody(message.body)}</div>
      </div>
    </div>
  )
}
