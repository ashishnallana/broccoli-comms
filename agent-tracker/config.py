import os
import tomllib
from pathlib import Path

def get_config_path() -> Path:
    xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return xdg_config / "broccoli-comms" / "config.toml"

def load_config() -> dict:
    path = get_config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}

def get(section: str, key: str, default=None):
    config = load_config()
    return config.get(section, {}).get(key, default)

def get_base_cache_dir() -> Path:
    configured = get("paths", "cache_dir")
    if configured:
        return Path(configured)
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))

def get_base_runtime_dir() -> Path:
    configured = get("paths", "runtime_dir")
    if configured:
        return Path(configured)
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime:
        return Path(xdg_runtime)
    try:
        uid = os.getuid()
        return Path(f"/tmp/{uid}/broccoli-comms")
    except AttributeError:
        import tempfile
        return Path(tempfile.gettempdir()) / "broccoli-comms"

