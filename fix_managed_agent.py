import re

with open("agent-registry/managed_agent.py", "r") as f:
    content = f.read()

content = re.sub(
    r'import logging\n',
    'import logging\nimport sys\nfrom pathlib import Path\n_repo_root = Path(__file__).resolve().parents[1]\nsys.path.insert(0, str(_repo_root / "agent-tracker"))\nimport config\n',
    content,
    count=1
)

content = content.replace(
    'tracker_socket = os.path.join(runtime_dir, "agent-tracker.sock")',
    'tracker_socket = config.get("paths", "agent_tracker_socket", os.path.join(runtime_dir, "agent-tracker.sock"))'
)

with open("agent-registry/managed_agent.py", "w") as f:
    f.write(content)
