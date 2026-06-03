import re

with open("commands.go", "r") as f:
    content = f.read()

content = re.sub(
    r'import \(',
    'import (\n\t"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"\n',
    content,
    count=1
)

content = content.replace(
    'ownTrackerID := os.Getenv("AGENT_TRACKER_ID")',
    'ownTrackerID := config.GetString("", "tracker", "tracker_id")\n\t\t\t\tif ownTrackerID == "" {\n\t\t\t\t\townTrackerID = os.Getenv("AGENT_TRACKER_ID")\n\t\t\t\t}'
)

content = content.replace(
    'ownHostname := os.Getenv("AGENT_TRACKER_HOSTNAME")',
    'ownHostname := config.GetString("", "tracker", "hostname")\n\t\t\t\tif ownHostname == "" {\n\t\t\t\t\townHostname = os.Getenv("AGENT_TRACKER_HOSTNAME")\n\t\t\t\t}'
)

with open("commands.go", "w") as f:
    f.write(content)
