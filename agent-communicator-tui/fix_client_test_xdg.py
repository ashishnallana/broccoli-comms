import re

with open("internal/tracker/client_test.go", "r") as f:
    content = f.read()

content = content.replace(
    't.Setenv("BROCCOLI_COMMS_RUNTIME_DIR", "/tmp/broccoli-runtime")',
    't.Setenv("BROCCOLI_COMMS_RUNTIME_DIR", "/tmp/broccoli-runtime")\n\tt.Setenv("XDG_RUNTIME_DIR", "")\n\tt.Setenv("XDG_CACHE_HOME", "")'
)

with open("internal/tracker/client_test.go", "w") as f:
    f.write(content)
