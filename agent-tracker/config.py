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
