import re

with open("agent_list.go", "r") as f:
    content = f.read()

content = re.sub(
    r'import \(',
    'import (\n\t"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"\n',
    content,
    count=1
)

content = content.replace(
    'cli := os.Getenv("BROCCOLI_COMMS_CLI")',
    'cli := config.GetString("", "executables", "agent_tracker_ctl")\n\tif cli == "" {\n\t\tcli = os.Getenv("BROCCOLI_COMMS_CLI")\n\t}'
)

with open("agent_list.go", "w") as f:
    f.write(content)
