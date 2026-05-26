interface Props {
  open: boolean
  onClose: () => void
}

export function ShortcutsPanel({ open, onClose }: Props) {
  return (
    <aside className={`shortcuts ${open ? 'open' : ''}`} id="shortcuts" aria-label="Keyboard shortcuts panel">
      <div className="shortcuts-head">
        <span className="shortcuts-title">Keyboard shortcuts</span>
        <button className="icon-btn" id="closeShortcuts" title="Close (?)" onClick={onClose}>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M4 4l8 8M12 4l-8 8" />
          </svg>
        </button>
      </div>
      <div className="shortcuts-body">
        <div className="shortcuts-group-title">Navigation</div>
        <div className="shortcut-row">
          <span>Next message</span>
          <span className="shortcut-keys"><kbd>j</kbd></span>
        </div>
        <div className="shortcut-row">
          <span>Previous message</span>
          <span className="shortcut-keys"><kbd>k</kbd></span>
        </div>
        <div className="shortcut-row">
          <span>Next channel</span>
          <span className="shortcut-keys"><kbd>]</kbd></span>
        </div>
        <div className="shortcut-row">
          <span>Previous channel</span>
          <span className="shortcut-keys"><kbd>[</kbd></span>
        </div>
        <div className="shortcut-row">
          <span>Jump to unread</span>
          <span className="shortcut-keys"><kbd>shift</kbd><kbd>u</kbd></span>
        </div>
        <div className="shortcut-row">
          <span>Scroll to bottom</span>
          <span className="shortcut-keys"><kbd>g</kbd><kbd>g</kbd></span>
        </div>

        <div className="shortcuts-group-title">Search & Jump</div>
        <div className="shortcut-row">
          <span>Command palette</span>
          <span className="shortcut-keys"><kbd>⌘</kbd><kbd>K</kbd></span>
        </div>
        <div className="shortcut-row">
          <span>Filter this channel</span>
          <span className="shortcut-keys"><kbd>/</kbd></span>
        </div>
        <div className="shortcut-row">
          <span>Focus composer</span>
          <span className="shortcut-keys"><kbd>r</kbd></span>
        </div>

        <div className="shortcuts-group-title">Stream</div>
        <div className="shortcut-row">
          <span>Pause / resume live</span>
          <span className="shortcut-keys"><kbd>Space</kbd></span>
        </div>
        <div className="shortcut-row">
          <span>Mark all read</span>
          <span className="shortcut-keys"><kbd>shift</kbd><kbd>esc</kbd></span>
        </div>

        <div className="shortcuts-group-title">Message</div>
        <div className="shortcut-row">
          <span>Pin focused message</span>
          <span className="shortcut-keys"><kbd>p</kbd></span>
        </div>
        <div className="shortcut-row">
          <span>Reply in thread</span>
          <span className="shortcut-keys"><kbd>t</kbd></span>
        </div>
        <div className="shortcut-row">
          <span>Copy message</span>
          <span className="shortcut-keys"><kbd>y</kbd></span>
        </div>

        <div className="shortcuts-group-title">Help</div>
        <div className="shortcut-row">
          <span>Show this panel</span>
          <span className="shortcut-keys"><kbd>?</kbd></span>
        </div>
      </div>
    </aside>
  )
}
