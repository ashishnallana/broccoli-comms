# Agent Communicator Color Theme Requirements

## Goal

Centralize all Agent Communicator TUI colors in one theme/color class so themes can be changed easily and the rest of the UI code uses semantic color roles instead of hard-coded color values.

## User requirement

> Have a color class where the color values are set and the rest of the code uses this color class. This allows us to change themes easily. Follow terminal color theme standards.

## Terminal color standard

Prefer ANSI terminal color indexes instead of fixed hex colors for the default theme. This lets the TUI inherit the user's terminal theme.

Use semantic roles backed by ANSI 16-color values:

| ANSI | Name | Typical role |
|---:|---|---|
| 0 | black | base/background |
| 1 | red | error |
| 2 | green | success/read/online |
| 3 | yellow | warning/waiting |
| 4 | blue | info/link |
| 5 | magenta | accent/secondary |
| 6 | cyan | primary/accent |
| 7 | white | foreground |
| 8 | bright black | muted/dim |
| 9 | bright red | strong error |
| 10 | bright green | strong success |
| 11 | bright yellow | strong warning |
| 12 | bright blue | strong info |
| 13 | bright magenta | strong accent |
| 14 | bright cyan | primary selected |
| 15 | bright white | strong foreground |

Lip Gloss accepts ANSI color strings, e.g.:

```go
lipgloss.Color("0")
lipgloss.Color("8")
lipgloss.Color("14")
```

Avoid direct hex colors like `#7fbbb3` in normal UI code. If hex palettes are kept, they must be isolated to a named alternate theme constructor only.

## Required implementation

Create or refactor a single color/theme module, for example:

```go
type TerminalTheme struct {
    BaseBg        lipgloss.Color
    PanelBg       lipgloss.Color
    PanelBgAlt    lipgloss.Color
    Text          lipgloss.Color
    TextStrong    lipgloss.Color
    Muted         lipgloss.Color
    Accent        lipgloss.Color
    AccentStrong  lipgloss.Color
    Success       lipgloss.Color
    Warning       lipgloss.Color
    Error         lipgloss.Color
    Info          lipgloss.Color
    Border        lipgloss.Color
    SelectedBg    lipgloss.Color
    SelectedFg    lipgloss.Color
    InputBg       lipgloss.Color
    PopupBg       lipgloss.Color
    PopupBorder   lipgloss.Color
    BadgeBg       lipgloss.Color
    BadgeFg       lipgloss.Color
    RemoteBadgeBg lipgloss.Color
    RemoteBadgeFg lipgloss.Color
    ReadTick      lipgloss.Color
    DeliveredTick lipgloss.Color
    SentTick      lipgloss.Color
    AgentColors   []lipgloss.Color
}

var colors = defaultTerminalTheme()
```

Names can differ, but they must be semantic roles, not palette color names like `Sky`, `Mauve`, `Peach` in view code.

## Usage requirement

All UI code must use semantic theme roles:

Good:

```go
lipgloss.NewStyle().Foreground(colors.Text).Background(colors.PanelBg)
lipgloss.NewStyle().Foreground(colors.Success)
lipgloss.NewStyle().Background(colors.SelectedBg).Foreground(colors.SelectedFg)
```

Avoid:

```go
lipgloss.NewStyle().Foreground(lipgloss.Color("#7fbbb3"))
lipgloss.NewStyle().Foreground(palette.Sky)
lipgloss.NewStyle().Background(palette.Surface0)
```

Exception: theme constructor files may contain actual color values.

## Theme constructors

Implement at least:

1. `defaultTerminalTheme()` using ANSI 16-color values.
2. Optional existing Everforest/Catppuccin-style theme can remain as an alternate constructor, but not as the default unless explicitly configured.

If adding runtime selection is easy, use an environment variable:

```sh
AGENT_COMMUNICATOR_THEME=terminal|everforest
```

If not, just centralize the default terminal theme and leave runtime selection for later.

## Tests

Add tests that ensure:

1. UI style code references semantic color object, not raw hex values outside theme constructor files.
2. Default theme uses ANSI color indexes, not hex.
3. Status colors map correctly:
   - online/idle -> success
   - waiting/pending -> warning
   - error/offline -> error
   - unknown -> muted
4. Read ticks use read/delivered/sent color roles.

Suggested lightweight test:

- scan `.go` files except the theme file and fail if they contain `lipgloss.Color("#` or direct hex color strings.

## Acceptance criteria

1. A single color/theme class or struct owns color values.
2. Default theme follows ANSI terminal color standards.
3. View/style/palette code uses semantic role names.
4. No direct hex colors in UI rendering code outside theme constructor file.
5. Existing TUI tests pass.
6. `nix build .#agentCommunicator` passes.
7. Capture-pane still visually matches the design mock after color refactor.
