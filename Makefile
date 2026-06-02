PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
GO ?= go
PYTHON ?= python3

.PHONY: build install check smoke-private-runtime smoke-default-session-reuse smoke-managed-agents clean

build:
	mkdir -p bin
	$(GO) -C agent-communicator-tui build -o ../bin/agent-communicator .
	cp app/broccoli-comms.py bin/broccoli-comms
	cp wrapper/agent-wrapper.sh bin/agent-wrapper
	printf '#!/usr/bin/env sh\nexec $(PYTHON) "%s/agent-tracker/agent-tracker.py" "$$@"\n' "$$(pwd)" > bin/agent-tracker
	printf '#!/usr/bin/env sh\necho "agent-tracker-ctl is deprecated. Use: broccoli-comms agent-tracker <subcommand> [args...]" >&2\nexit 1\n' > bin/agent-tracker-ctl
	chmod +x bin/broccoli-comms bin/agent-wrapper bin/agent-tracker bin/agent-tracker-ctl

install: build
	mkdir -p $(BINDIR)
	cp bin/broccoli-comms bin/agent-wrapper bin/agent-tracker bin/agent-tracker-ctl bin/agent-communicator $(BINDIR)/

check:
	$(PYTHON) -m py_compile app/broccoli-comms.py agent-tracker/*.py agent-registry/*.py
	$(GO) -C agent-communicator-tui test ./...

smoke-private-runtime:
	bash scripts/smoke-private-runtime.sh

smoke-default-session-reuse:
	bash scripts/smoke-default-session-reuse.sh

smoke-managed-agents:
	bash scripts/smoke-managed-agents.sh

clean:
	rm -rf bin
