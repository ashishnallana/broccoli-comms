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

interface PaneCaptureDetails {
  author: string
  pane: string
  session: string
  copyMode: string
  capturedAt: string
  content: string
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

function renderInlineFormatting(text: string): ReactNode {
  let parts: any[] = [text]

  // A. Bold processing (split by **)
  if (text.includes('**')) {
    const boldParts = text.split('**')
    parts = boldParts.map((part, idx) => {
      if (idx % 2 === 1) return <strong key={`b-${idx}`} style={{ fontWeight: 700, color: 'var(--on-dark)' }}>{part}</strong>
      return part
    })
  }

  // B. Inline code processing (split by `)
  const partsWithCode: any[] = []
  parts.forEach((part, pIdx) => {
    if (typeof part !== 'string') {
      partsWithCode.push(part)
      return
    }
    if (!part.includes('`')) {
      partsWithCode.push(part)
      return
    }
    const codeParts = part.split('`')
    codeParts.forEach((cPart, idx) => {
      if (idx % 2 === 1) {
        partsWithCode.push(
          <code
            key={`c-${pIdx}-${idx}`}
            style={{
              background: 'var(--surface-soft)',
              border: '1px solid var(--hairline)',
              borderRadius: 'var(--r-sm)',
              padding: '1px 4px',
              fontSize: '11.5px',
              color: 'var(--primary)',
              fontFamily: 'var(--mono)',
            }}
          >
            {cPart}
          </code>
        )
      } else {
        partsWithCode.push(cPart)
      }
    })
  })
  parts = partsWithCode

  // C. Markdown Links [text](url)
  const finalParts: any[] = []
  parts.forEach((part, pIdx) => {
    if (typeof part !== 'string') {
      finalParts.push(part)
      return
    }
    const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g
    const matches = [...part.matchAll(linkRegex)]
    if (matches.length === 0) {
      finalParts.push(part)
      return
    }

    let lastIndex = 0
    matches.forEach((match, mIdx) => {
      const matchIndex = match.index ?? 0
      const linkText = match[1]
      const url = match[2]

      if (matchIndex > lastIndex) {
        finalParts.push(part.slice(lastIndex, matchIndex))
      }

      finalParts.push(
        <a
          key={`link-${pIdx}-${mIdx}`}
          href={url}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => {
            if (url.startsWith('file://')) {
              e.preventDefault()
              window.open(url, '_blank')
            }
          }}
          style={{
            color: 'var(--accent-blue)',
            textDecoration: 'underline',
            cursor: 'pointer',
          }}
        >
          {linkText}
        </a>
      )
      lastIndex = matchIndex + match[0].length
    })

    if (lastIndex < part.length) {
      finalParts.push(part.slice(lastIndex))
    }
  })

  return <>{finalParts}</>
}

function renderMarkdown(text: string): ReactNode {
  const lines = text.split('\n')
  let inList = false
  const listElements: ReactNode[] = []
  const resultElements: ReactNode[] = []

  function flushList() {
    if (listElements.length > 0) {
      resultElements.push(
        <ul key={`list-${resultElements.length}`} style={{ margin: '4px 0 8px 20px', padding: 0 }}>
          {listElements.map((el, i) => (
            <li key={i} style={{ marginBottom: '4px' }}>
              {el}
            </li>
          ))}
        </ul>
      )
      listElements.length = 0
      inList = false
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // 1. Fenced Code Blocks
    if (line.startsWith('```')) {
      flushList()
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      resultElements.push(
        <pre
          key={`code-${i}`}
          style={{
            background: 'var(--surface-soft)',
            border: '1px solid var(--hairline)',
            borderRadius: 'var(--r-md)',
            padding: '10px 12px',
            overflowX: 'auto',
            fontSize: '12.5px',
            fontFamily: 'var(--mono)',
            margin: '8px 0',
          }}
        >
          {codeLines.join('\n')}
        </pre>
      )
      continue
    }

    // 2. Headings
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/)
    if (headingMatch) {
      flushList()
      const level = headingMatch[1].length
      const title = renderInlineFormatting(headingMatch[2])
      const fontSize = level === 1 ? '18px' : level === 2 ? '16px' : '14px'
      const marginTop = level === 1 ? '16px' : '12px'
      resultElements.push(
        <div
          key={`h-${i}`}
          style={{
            fontSize,
            fontWeight: 700,
            color: 'var(--on-dark)',
            marginTop,
            marginBottom: '6px',
            fontFamily: 'inherit',
          }}
        >
          {title}
        </div>
      )
      continue
    }

    // 3. Bullet List Items
    const listMatch = line.match(/^[-*]\s+(.+)$/)
    if (listMatch) {
      inList = true
      listElements.push(renderInlineFormatting(listMatch[1]))
      continue
    }

    // Empty line flushes bullet lists
    if (inList && line.trim() === '') {
      flushList()
      continue
    }

    // 4. Regular Paragraphs
    if (line.trim() !== '') {
      flushList()
      resultElements.push(
        <p key={`p-${i}`} style={{ margin: '4px 0 6px', lineHeight: '1.5' }}>
          {renderInlineFormatting(line)}
        </p>
      )
    } else {
      flushList()
    }
  }
  flushList()

  return <>{resultElements}</>
}

function parsePaneCapture(body: string): PaneCaptureDetails | null {
  if (!body.startsWith('### Pane Capture Snapshot from') && !body.startsWith('### Mock Pane Capture Snapshot from')) {
    return null
  }
  const lines = body.split('\n')
  let author = 'Agent'
  let pane = 'unknown'
  let session = 'unknown'
  let copyMode = 'Inactive'
  let capturedAt = ''
  let content = ''

  const authorMatch = lines[0].match(/from\s+(.+)$/)
  if (authorMatch) author = authorMatch[1]

  lines.forEach((line) => {
    if (line.startsWith('- **Pane:**')) pane = line.replace('- **Pane:**', '').trim()
    if (line.startsWith('- **Session:**')) session = line.replace('- **Session:**', '').trim()
    if (line.startsWith('- **Copy Mode:**')) copyMode = line.replace('- **Copy Mode:**', '').trim()
    if (line.startsWith('- **Captured At:**')) capturedAt = line.replace('- **Captured At:**', '').trim()
  })

  const codeStartIndex = body.indexOf('```\n')
  const codeEndIndex = body.lastIndexOf('\n```')
  if (codeStartIndex !== -1 && codeEndIndex !== -1 && codeEndIndex > codeStartIndex) {
    content = body.slice(codeStartIndex + 4, codeEndIndex).trim()
  } else {
    const contentLines = lines.filter((l) => !l.startsWith('#') && !l.startsWith('-') && !l.startsWith('```') && l.trim() !== '')
    content = contentLines.join('\n')
  }

  return { author, pane, session, copyMode, capturedAt, content }
}

export function MessageBubble({ message, grouped = false, focused = false, onFocus }: Props) {
  const details = parsePaneCapture(message.body)
  const displayAuthor = message.direction === 'outbound' ? 'you' : message.author
  const fullTimeStr = formatTime(message.createdAt)
  const timeParts = fullTimeStr.split(' ')
  const shortTime = timeParts[timeParts.length - 1]

  if (details) {
    return (
      <div className={`msg-row pane-capture ${focused ? 'focused' : ''}`} tabIndex={0} onFocus={onFocus}>
        <div className="msg-gutter">
          <div className="msg-avatar-wrap">
            <div className="msg-avatar" style={{ background: 'var(--hairline-strong)', border: '1px solid var(--hairline)' }}>
              🖥️
            </div>
          </div>
        </div>
        <div className="msg-content">
          <div className="msg-author">
            <span className="msg-author-name">{displayAuthor}</span>
            <span className="msg-author-arrow">→</span>
            <span className="msg-author-recipient">
              {message.direction === 'outbound' ? `@${message.conversationKey}` : '#group'}
            </span>
            <span
              className="msg-kind tool"
              style={{
                color: 'var(--accent-amber)',
                borderColor: 'rgba(245, 158, 11, 0.2)',
                background: 'rgba(245, 158, 11, 0.06)',
              }}
            >
              Pane Snapshot
            </span>
            <span className="msg-author-time">{fullTimeStr}</span>
          </div>

          {/* Terminal emulation window */}
          <div
            className="terminal-window"
            style={{
              marginTop: '8px',
              background: '#000000',
              border: '1px solid var(--hairline)',
              borderRadius: 'var(--r-md)',
              overflow: 'hidden',
              boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
            }}
          >
            <div
              className="terminal-titlebar"
              style={{
                height: '28px',
                background: '#161616',
                borderBottom: '1px solid var(--hairline)',
                display: 'flex',
                alignItems: 'center',
                padding: '0 12px',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', gap: '5px' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#ff5f56' }}></span>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#ffbd2e' }}></span>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#27c93f' }}></span>
              </div>
              <div
                style={{
                  flex: 1,
                  textAlign: 'center',
                  fontSize: '11px',
                  fontFamily: '"JetBrains Mono", monospace',
                  color: 'var(--muted)',
                  marginRight: '24px',
                }}
              >
                tmux:{details.pane} ({details.session}) · {details.copyMode === 'Active' ? 'copy-mode' : 'normal'}
              </div>
            </div>
            <pre
              className="terminal-screen"
              style={{
                padding: '12px 14px',
                margin: 0,
                background: '#020202',
                border: 0,
                borderRadius: 0,
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: '12px',
                lineHeight: '1.45',
                color: '#22c55e',
                overflowX: 'auto',
                maxHeight: '380px',
              }}
            >
              {details.content}
            </pre>
          </div>
        </div>
      </div>
    )
  }

  const kind = inferKind(message.body)

  return (
    <div className={`msg-row ${grouped ? 'grouped' : ''} ${focused ? 'focused' : ''}`} tabIndex={0} onFocus={onFocus}>
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
        <div className="msg-body">{renderMarkdown(message.body)}</div>
      </div>
    </div>
  )
}
