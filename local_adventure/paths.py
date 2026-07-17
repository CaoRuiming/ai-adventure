"""Runtime-location helpers."""

from __future__ import annotations

import os
from pathlib import Path


def runtime_root() -> Path:
    """Return the local runtime root, honoring the explicitly named override."""
    configured = os.environ.get("LOCAL_ADVENTURE_HOME")
    return Path(configured).expanduser() if configured else Path.cwd() / ".local-adventure"


def database_path() -> Path:
    """Return the SQLite database location, creating only the runtime directory."""
    root = runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "local-adventure.sqlite3"
