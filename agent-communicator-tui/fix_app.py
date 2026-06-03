import re

with open("app.go", "r") as f:
    content = f.read()

content = re.sub(
    r'import \(',
    'import (\n\t"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"\n',
    content,
    count=1
)

content = content.replace(
    'RuntimeDir:    os.Getenv("BROCCOLI_COMMS_RUNTIME_DIR"),',
    'RuntimeDir:    firstNonEmpty(config.GetString("", "paths", "runtime_dir"), os.Getenv("BROCCOLI_COMMS_RUNTIME_DIR")),'
)

content = content.replace(
    'TrackerSocket: os.Getenv("AGENT_TRACKER_SOCKET"),',
    'TrackerSocket: firstNonEmpty(config.GetString("", "paths", "agent_tracker_socket"), os.Getenv("AGENT_TRACKER_SOCKET")),'
)

content = content.replace(
    'TmuxSocket:    firstNonEmpty(os.Getenv("BROCCOLI_COMMS_TMUX_SOCKET"), os.Getenv("AGENT_TRACKER_TMUX_SOCKET")),',
    'TmuxSocket:    firstNonEmpty(config.GetString("", "paths", "tmux_socket"), os.Getenv("BROCCOLI_COMMS_TMUX_SOCKET"), os.Getenv("AGENT_TRACKER_TMUX_SOCKET")),'
)

content = content.replace(
    'info.AppRuntime = os.Getenv("BROCCOLI_COMMS_APP_RUNTIME") == "1" || info.RuntimeDir != "" || os.Getenv("BROCCOLI_COMMS_TMUX_SOCKET") != ""',
    'info.AppRuntime = os.Getenv("BROCCOLI_COMMS_APP_RUNTIME") == "1" || info.RuntimeDir != "" || info.TmuxSocket != ""'
)

content = content.replace(
    'info.RemoteDirectInputEnabled = envEnabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED") || envEnabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_SEND_ENABLED") || envEnabled("AGENT_TRACKER_REMOTE_PANE_INPUT_SEND_ENABLED")',
    'info.RemoteDirectInputEnabled = config.GetBool(false, "ui", "remote_pane_input_enabled") || envEnabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED") || envEnabled("BROCCOLI_COMMS_REMOTE_PANE_INPUT_SEND_ENABLED") || envEnabled("AGENT_TRACKER_REMOTE_PANE_INPUT_SEND_ENABLED")'
)

with open("app.go", "w") as f:
    f.write(content)
