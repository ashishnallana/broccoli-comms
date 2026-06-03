import re

with open("view.go", "r") as f:
    content = f.read()

content = re.sub(
    r'import \(',
    'import (\n\t"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"\n',
    content,
    count=1
)

content = content.replace(
    'if h := os.Getenv("AGENT_TRACKER_HOSTNAME"); h != "" {',
    'if h := config.GetString("", "tracker", "hostname"); h != "" {\n\t\thostname = h\n\t} else if h := os.Getenv("AGENT_TRACKER_HOSTNAME"); h != "" {'
)

with open("view.go", "w") as f:
    f.write(content)
