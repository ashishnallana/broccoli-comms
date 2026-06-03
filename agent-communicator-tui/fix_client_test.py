import re

with open("internal/tracker/client_test.go", "r") as f:
    content = f.read()

content = re.sub(
    r'import \(',
    'import (\n\t"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"\n',
    content,
    count=1
)

content = content.replace(
    't.Setenv("AGENT_TRACKER_SOCKET", "")',
    'config.ResetForTest()\n\tt.Setenv("XDG_CONFIG_HOME", "/dev/null")\n\tt.Setenv("AGENT_TRACKER_SOCKET", "")'
)

content = content.replace(
    't.Setenv("AGENT_TRACKER_SOCKET", "/tmp/private/tracker.sock")',
    'config.ResetForTest()\n\tt.Setenv("XDG_CONFIG_HOME", "/dev/null")\n\tt.Setenv("AGENT_TRACKER_SOCKET", "/tmp/private/tracker.sock")'
)

with open("internal/tracker/client_test.go", "w") as f:
    f.write(content)
