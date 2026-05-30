# Broccoli Comms registry URL configuration plan

## Goal

Add first-class commands for configuring the registry URLs that the Broccoli Comms private tracker publishes to and reads from.

This is distinct from running a registry server:

- `broccoli-comms registry start ...` runs an `agent-registry` process.
- `broccoli-comms registry add ...` configures this local Broccoli Comms tracker to use a registry URL.

Target user flow:

```sh
broccoli-comms registry add --name home --url https://agents.example.com --token-file ~/.config/broccoli-comms/registry-token
broccoli-comms restart  # or stop/start if restart is not available
broccoli-comms agent-tracker registry-status
```

Local development flow:

```sh
broccoli-comms registry start --host 127.0.0.1 --port 8080 --name local --noauth
broccoli-comms registry add --name local --url http://127.0.0.1:8080 --noauth
broccoli-comms restart
broccoli-comms agent-tracker registry-status
```

## Storage location

Store configured registry URLs in Broccoli Comms' config directory:

```text
$BROCCOLI_COMMS_CONFIG_DIR/registries.json
```

Default path:

```text
~/.config/broccoli-comms/registries.json
```

Do not store runtime-only state here. Registry server pid/log/state stay in runtime/cache paths from `docs/BROCCOLI_REGISTRY_COMMAND_PLAN.md`.

## File schema

Use a versioned object, not a bare list, so future fields can be added without migrations:

```json
{
  "version": 1,
  "registries": [
    {
      "name": "home",
      "url": "https://agents.example.com",
      "token-file": "/home/tanmay/.config/broccoli-comms/registry-token",
      "enabled": true
    },
    {
      "name": "local",
      "url": "http://127.0.0.1:8080",
      "auth": false,
      "enabled": true
    }
  ]
}
```

Canonical keys for tracker compatibility should use the existing tracker names:

- `name`
- `url`
- `token-file`
- `token` only when explicitly requested; prefer not to support storing raw token values initially

Broccoli-only metadata:

- `enabled`: default true
- `auth`: optional UI/CLI hint; tracker primarily cares about token/token-file
- future fields such as `created_at`, `updated_at`, `description`

When constructing `AGENT_REGISTRIES_JSON`, pass only enabled tracker-compatible entries. Strip Broccoli-only metadata unless the tracker tolerates it.

Generated env example:

```json
[
  {"name":"home","url":"https://agents.example.com","token-file":"/home/tanmay/.config/broccoli-comms/registry-token"},
  {"name":"local","url":"http://127.0.0.1:8080"}
]
```

## CLI commands

Add these under the existing/proposed `registry` namespace.

### `broccoli-comms registry add`

Configure or replace one registry URL.

```text
broccoli-comms registry add --name NAME --url URL [--token-file PATH] [--auth|--noauth] [--replace]
```

Behavior:

- Validate `NAME` with the same conservative naming style as agent names: `[A-Za-z0-9_.-]+`.
- Validate `URL` scheme is `http://` or `https://`.
- Normalize URL by removing trailing slash except root.
- If name exists, fail unless `--replace` is passed.
- If `--auth` is passed, require `--token-file` for the initial implementation.
- If `--noauth` is passed, write no token field.
- Do not read or print token contents.
- Create config dir and `registries.json` if missing.
- Write atomically with mode `0600` or as restrictive as practical.

Examples:

```sh
broccoli-comms registry add --name home --url https://agents.example.com --auth --token-file ~/.config/broccoli-comms/registry-token
broccoli-comms registry add --name local --url http://127.0.0.1:8080 --noauth
broccoli-comms registry add --name local --url http://127.0.0.1:18080 --noauth --replace
```

### `broccoli-comms registry list`

Show configured registry URLs.

```text
broccoli-comms registry list [--json]
```

Human output should redact secrets and show only token file paths:

```text
NAME   URL                         AUTH         ENABLED
home   https://agents.example.com  token-file   yes
local  http://127.0.0.1:8080       noauth       yes
```

`--json` should emit the stored config with no token values. Since the initial implementation should not store raw tokens, redaction is mainly future-proofing.

### `broccoli-comms registry remove`

Remove a configured registry by name.

```text
broccoli-comms registry remove NAME
```

Fail if missing unless `--missing-ok` is added.

### `broccoli-comms registry enable` / `disable`

Optional but useful:

```text
broccoli-comms registry disable NAME
broccoli-comms registry enable NAME
```

This toggles `enabled` without deleting the saved URL.

### `broccoli-comms registry env`

Debug/inspection command:

```text
broccoli-comms registry env [--json]
```

Print the `AGENT_REGISTRIES_JSON` that would be supplied to the private tracker, with token values redacted if raw token support is ever added.

## Integration with `broccoli-comms start`

Update `base_env()` or a helper it calls so the private tracker automatically receives configured registries.

Recommended rule:

1. Start with `os.environ.copy()` as today.
2. If caller already supplied `AGENT_REGISTRIES_JSON`, preserve it exactly. Explicit environment wins.
3. Otherwise, load `$BROCCOLI_COMMS_CONFIG_DIR/registries.json`.
4. Filter `enabled != false`.
5. Convert to tracker-compatible JSON list.
6. Set `env["AGENT_REGISTRIES_JSON"]` when the resulting list is non-empty.

This preserves current power-user behavior while making CLI-configured registries automatic.

Add an opt-out if useful:

```sh
BROCCOLI_COMMS_DISABLE_CONFIG_REGISTRIES=1 broccoli-comms start
```

## Restart behavior

Changing registry configuration affects newly started tracker processes. The initial implementation can document that users must restart Broccoli Comms:

```sh
broccoli-comms stop
broccoli-comms start
```

If a `restart` command exists or is added later:

```sh
broccoli-comms restart
```

Optional enhancement: after `registry add/remove/enable/disable`, print:

```text
Registry configuration updated. Restart Broccoli Comms for changes to affect the running tracker.
```

A future enhancement can hot-reload registries through tracker RPC. Do not require that for this implementation.

## Interaction with `registry start --name`

`registry start --name local --host 127.0.0.1 --port 8080 --noauth` should persist server metadata in its own config, but it should not silently modify tracker registry URLs unless explicitly requested.

Optional convenience flags:

```text
broccoli-comms registry start ... --add-to-tracker
broccoli-comms registry start ... --add-to-tracker --replace
```

If implemented, this should internally call the same registry config writer used by `registry add`.

Default should stay explicit to avoid surprising tracker routing changes.

## Security requirements

- Prefer token files; do not store raw token values in `registries.json` for the initial implementation.
- If `--token` support is later added, require `--store-token` or write it into a separate `0600` token file, not directly into the JSON by default.
- Never print token contents in normal, `--json`, or error output.
- Keep remote direct pane input disabled by default. Configuring a registry URL must not set any of:
  - `AGENT_REMOTE_PANE_INPUT_ENABLED`
  - `AGENT_REGISTRY_REMOTE_PANE_INPUT_ENABLED`
  - `BROCCOLI_COMMS_REMOTE_PANE_INPUT_*`
- Warn when adding an unauthenticated non-loopback HTTP registry URL if desired, but do not block adding remote noauth URLs unconditionally because local labs may use private networks. Strong docs warning is required.

## Implementation details

### Paths

Add to `paths()`:

```py
"registries_json": config / "registries.json"
```

### Helpers

Add helper functions in `app/broccoli-comms.py`:

```py
def load_registry_config() -> dict:
    ...

def save_registry_config(config: dict) -> None:
    ...  # atomic write, mode 0600

def configured_registries_for_tracker() -> list[dict[str, str]]:
    ...

def apply_configured_registries(env: dict[str, str]) -> dict[str, str]:
    ...
```

`save_registry_config` should:

- create config dir
- write to a temporary file in the same directory
- `json.dump(..., indent=2, sort_keys=True)`
- `os.chmod(temp, 0o600)`
- `os.replace(temp, registries_json)`

### Parser

Extend the `registry` subparser with nested subcommands:

```py
registry_sub = registry_parser.add_subparsers(dest="registry_command", required=True)

add = registry_sub.add_parser("add", help="Configure a registry URL for the private tracker")
add.add_argument("--name", required=True)
add.add_argument("--url", required=True)
add.add_argument("--auth", action="store_true")
add.add_argument("--noauth", action="store_true")
add.add_argument("--token-file")
add.add_argument("--replace", action="store_true")

registry_sub.add_parser("list", ...)
registry_sub.add_parser("remove", ...)
registry_sub.add_parser("enable", ...)
registry_sub.add_parser("disable", ...)
registry_sub.add_parser("env", ...)
```

Use mutually exclusive groups for `--auth` and `--noauth`.

### Base env hook

In `base_env()` after setting core private runtime env:

```py
if "AGENT_REGISTRIES_JSON" not in os.environ and os.environ.get("BROCCOLI_COMMS_DISABLE_CONFIG_REGISTRIES") not in ("1", "true", "yes"):
    registries = configured_registries_for_tracker()
    if registries:
        env["AGENT_REGISTRIES_JSON"] = json.dumps(registries)
```

Be careful to avoid recursion if helper uses `base_env()`.

## Tests and smoke validation

### Unit-style checks

If no app-level test harness exists, add one or perform focused script validation.

Test cases:

1. Missing config returns no registries and does not set `AGENT_REGISTRIES_JSON`.
2. `registry add --name local --url http://127.0.0.1:8080 --noauth` creates `registries.json`.
3. `registry add` duplicate fails without `--replace`.
4. `registry add --replace` updates URL.
5. `registry add --auth --token-file /tmp/token` writes `token-file`, not token contents.
6. `registry list --json` emits valid JSON and no token contents.
7. `registry remove local` removes entry.
8. `base_env()` preserves explicit inherited `AGENT_REGISTRIES_JSON`.
9. `base_env()` sets configured registries when env is absent.
10. Disabled entries are not included in generated `AGENT_REGISTRIES_JSON`.

### Smoke commands

Use isolated dirs:

```sh
export BROCCOLI_COMMS_RUNTIME_DIR=/tmp/bc-reg-url-runtime
export BROCCOLI_COMMS_CACHE_DIR=/tmp/bc-reg-url-cache
export BROCCOLI_COMMS_CONFIG_DIR=/tmp/bc-reg-url-config
rm -rf "$BROCCOLI_COMMS_RUNTIME_DIR" "$BROCCOLI_COMMS_CACHE_DIR" "$BROCCOLI_COMMS_CONFIG_DIR"

python app/broccoli-comms.py registry add --name local --url http://127.0.0.1:18080 --noauth
python app/broccoli-comms.py registry list
python app/broccoli-comms.py registry list --json
python app/broccoli-comms.py registry env --json
python app/broccoli-comms.py registry remove local
python app/broccoli-comms.py registry list --json
```

Integration with tracker:

```sh
python app/broccoli-comms.py registry add --name local --url http://127.0.0.1:18080 --noauth
python app/broccoli-comms.py start
python app/broccoli-comms.py agent-tracker registry-status
python app/broccoli-comms.py stop
```

For a full local server flow after `registry start` exists:

```sh
python app/broccoli-comms.py registry start --host 127.0.0.1 --port 18080 --name local --noauth
python app/broccoli-comms.py registry add --name local --url http://127.0.0.1:18080 --noauth --replace
python app/broccoli-comms.py start
python app/broccoli-comms.py agent-tracker registry-status
python app/broccoli-comms.py registry stop
python app/broccoli-comms.py stop
```

## Documentation updates

Update:

- `README.md`
- `docs/SETUP_AND_MULTI_DEVICE.md`
- `docs/RUNTIME_API.md` if runtime env/config behavior is documented there

Document:

- Where registry URLs are stored: `$BROCCOLI_COMMS_CONFIG_DIR/registries.json`
- `registry add/list/remove/enable/disable/env`
- Explicit env `AGENT_REGISTRIES_JSON` overrides saved config
- Restart requirement
- Token-file recommendation
- Difference between running a registry server and configuring tracker registry URLs

## Acceptance criteria

- `broccoli-comms registry add --name home --url https://agents.example.com --token-file <file> --auth` persists the URL in `$BROCCOLI_COMMS_CONFIG_DIR/registries.json`.
- `broccoli-comms registry list` and `list --json` show saved registries without leaking secrets.
- `broccoli-comms registry remove home` removes a saved registry.
- `broccoli-comms start` automatically passes saved enabled registries to the private tracker via `AGENT_REGISTRIES_JSON`.
- Explicit inherited `AGENT_REGISTRIES_JSON` still wins over saved config.
- `registry add/remove` does not enable remote pane-input gates.
- Docs explain storage, restart, and security behavior.
