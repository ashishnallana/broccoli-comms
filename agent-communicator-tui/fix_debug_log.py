import re

with open("debug_log.go", "r") as f:
    content = f.read()

content = re.sub(
    r'import \(',
    'import (\n\t"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"\n',
    content,
    count=1
)

content = content.replace(
    'path := os.Getenv("AGENT_COMMUNICATOR_DEBUG_LOG")',
    'path := config.GetString("", "ui", "debug_log")\n\tif path == "" {\n\t\tpath = os.Getenv("AGENT_COMMUNICATOR_DEBUG_LOG")\n\t}'
)

with open("debug_log.go", "w") as f:
    f.write(content)
