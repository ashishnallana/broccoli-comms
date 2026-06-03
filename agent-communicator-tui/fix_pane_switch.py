import re

with open("pane_switch.go", "r") as f:
    content = f.read()

content = re.sub(
    r'import \(',
    'import (\n\t"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"\n',
    content,
    count=1
)

content = content.replace(
    'return firstNonEmpty(os.Getenv("AGENT_TRACKER_TMUX_SOCKET"), os.Getenv("BROCCOLI_COMMS_TMUX_SOCKET"))',
    'return firstNonEmpty(config.GetString("", "paths", "tmux_socket"), os.Getenv("AGENT_TRACKER_TMUX_SOCKET"), os.Getenv("BROCCOLI_COMMS_TMUX_SOCKET"))'
)

with open("pane_switch.go", "w") as f:
    f.write(content)
