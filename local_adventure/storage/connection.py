"""SQLite connection setup for the local runtime database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..errors import DatabaseError


def open_connection(database_path: str | Path) -> sqlite3.Connection:
    """Open a configured SQLite connection with named-column rows enabled."""
    try:
        connection = sqlite3.connect(str(database_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
    except sqlite3.Error as error:
        raise DatabaseError(f"unable to open database '{database_path}': {error}") from error
