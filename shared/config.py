"""Load settings from a .env file and the environment.

Usage:
    from shared.config import load_env, require
    load_env("tenant-desk/.env")
    token = require("WHATSAPP_TOKEN")
"""
import os
from pathlib import Path


def load_env(path):
    """Read KEY=VALUE lines from a .env file into os.environ.

    Values already set in the real environment win, so tests and
    Lambda settings are not overwritten. A missing file is not an error.
    """
    env_file = Path(path)
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require(name):
    """Return a setting, or stop with a clear message if it is missing."""
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Missing setting {name}. Add it to your .env file.")
    return value


def optional(name, default=""):
    """Return a setting, or the default if it is not set."""
    return os.environ.get(name, default)
