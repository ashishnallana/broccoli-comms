import { useEffect, useMemo, useRef, useState } from 'react'
import type { AgentSummary } from '../../shared/contracts'

interface Props {
  open: boolean
  agents: AgentSummary[]
  onSelectAgent: (agent: AgentSummary) => void
  onClose: () => void
}

export function CommandPalette({ open, agents, onSelectAgent, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setQuery('')
      setSelectedIndex(0)
      // Small timeout to ensure modal is fully rendered and can be focused
      const timer = setTimeout(() => inputRef.current?.focus(), 50)
      return () => clearTimeout(timer)
    }
    return undefined
  }, [open])

  const normalizedQuery = query.trim().toLowerCase()

  // Filtered items partitioned by category
  const filteredChannels = useMemo(() => {
    return agents
      .filter((a) => a.displayName.toLowerCase().includes(normalizedQuery) || a.project.toLowerCase().includes(normalizedQuery))
      .map((a) => ({
        type: 'channel' as const,
        id: a.id,
        label: a.displayName,
        meta: `${a.project} · ${a.scope}`,
        agent: a,
      }))
  }, [agents, normalizedQuery])

  const actions = useMemo(() => {
    const list = [
      { type: 'action' as const, id: 'action-shortcuts', label: 'Show keyboard shortcuts', meta: '?' },
      { type: 'action' as const, id: 'action-close', label: 'Close palette', meta: 'esc' },
    ]
    if (!normalizedQuery) return list
    return list.filter((act) => act.label.toLowerCase().includes(normalizedQuery))
  }, [normalizedQuery])

  // Flattened list for keyboard up/down index tracking
  const flattenedItems = useMemo(() => {
    return [...filteredChannels, ...actions]
  }, [filteredChannels, actions])

  useEffect(() => {
    setSelectedIndex(0)
  }, [flattenedItems.length])

  useEffect(() => {
    if (!open) return

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((prev) => (flattenedItems.length === 0 ? 0 : (prev + 1) % flattenedItems.length))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((prev) =>
          flattenedItems.length === 0 ? 0 : (prev - 1 + flattenedItems.length) % flattenedItems.length,
        )
      } else if (e.key === 'Enter') {
        e.preventDefault()
        const activeItem = flattenedItems[selectedIndex]
        if (activeItem) {
          if (activeItem.type === 'channel') {
            onSelectAgent(activeItem.agent)
          } else if (activeItem.id === 'action-shortcuts') {
            // Small delay to avoid key capturing collision
            setTimeout(() => {
              const event = new KeyboardEvent('keydown', { key: '?' })
              document.dispatchEvent(event)
            }, 50)
          }
          onClose()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, flattenedItems, selectedIndex, onSelectAgent, onClose])

  if (!open) return null

  return (
    <div
      className="palette-backdrop open"
      id="paletteBackdrop"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="palette" id="palette">
        <div className="palette-input-wrap">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <circle cx="7" cy="7" r="5" />
            <line x1="11" y1="11" x2="14" y2="14" strokeLinecap="round" />
          </svg>
          <input
            ref={inputRef}
            className="palette-input"
            id="paletteInput"
            placeholder="Jump to channel, agent, command…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <kbd>esc</kbd>
        </div>
        <div className="palette-results">
          {filteredChannels.length > 0 && (
            <>
              <div className="palette-section-head">Channels / Agents</div>
              {filteredChannels.map((item, idx) => {
                const globalIdx = idx
                const isSelected = globalIdx === selectedIndex
                return (
                  <button
                    key={item.id}
                    className={`palette-row ${isSelected ? 'selected' : ''}`}
                    onMouseEnter={() => setSelectedIndex(globalIdx)}
                    onClick={() => {
                      onSelectAgent(item.agent)
                      onClose()
                    }}
                  >
                    <div className="palette-row-icon">#</div>
                    <div className="palette-row-label">{item.label}</div>
                    <div className="palette-row-meta">{item.meta}</div>
                  </button>
                )
              })}
            </>
          )}

          {actions.length > 0 && (
            <>
              <div className="palette-section-head">Actions</div>
              {actions.map((item, idx) => {
                const globalIdx = filteredChannels.length + idx
                const isSelected = globalIdx === selectedIndex
                return (
                  <button
                    key={item.id}
                    className={`palette-row ${isSelected ? 'selected' : ''}`}
                    onMouseEnter={() => setSelectedIndex(globalIdx)}
                    onClick={() => {
                      if (item.id === 'action-shortcuts') {
                        setTimeout(() => {
                          const event = new KeyboardEvent('keydown', { key: '?' })
                          document.dispatchEvent(event)
                        }, 50)
                      }
                      onClose()
                    }}
                  >
                    <div className="palette-row-icon">⚙</div>
                    <div className="palette-row-label">{item.label}</div>
                    <div className="palette-row-meta">{item.meta}</div>
                  </button>
                )
              })}
            </>
          )}

          {flattenedItems.length === 0 && (
            <div className="empty-card">No results found matching "{query}"</div>
          )}
        </div>
        <div className="palette-footer">
          <span className="palette-footer-item">
            <kbd>↑</kbd>
            <kbd>↓</kbd> navigate
          </span>
          <span className="palette-footer-item">
            <kbd>↵</kbd> open
          </span>
          <span className="palette-footer-item">
            <kbd>esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  )
}
