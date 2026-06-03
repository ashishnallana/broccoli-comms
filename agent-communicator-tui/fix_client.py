import re

with open("internal/tracker/client.go", "r") as f:
    content = f.read()

content = re.sub(
    r'import \(',
    'import (\n\t"github.com/tanmayvijay/home-manager-core/agent-communicator-tui/internal/config"\n',
    content,
    count=1
)

content = content.replace(
    'if path := os.Getenv("AGENT_TRACKER_SOCKET"); path != "" {',
    'if path := config.GetString("", "paths", "agent_tracker_socket"); path != "" {\n\t\treturn path, nil\n\t}\n\tif path := os.Getenv("AGENT_TRACKER_SOCKET"); path != "" {'
)

content = content.replace(
    'if runtimeDir := os.Getenv("BROCCOLI_COMMS_RUNTIME_DIR"); runtimeDir != "" {',
    'if runtimeDir := config.GetString("", "paths", "runtime_dir"); runtimeDir != "" {\n\t\tpath := filepath.Join(runtimeDir, "agent-tracker.sock")\n\t\treturn path, nil\n\t}\n\tif runtimeDir := os.Getenv("BROCCOLI_COMMS_RUNTIME_DIR"); runtimeDir != "" {'
)

with open("internal/tracker/client.go", "w") as f:
    f.write(content)
