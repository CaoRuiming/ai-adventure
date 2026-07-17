"""Ordered, transactional SQLite schema migrations."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from ..errors import MigrationError
from ..util.clocks import Clock, utc_now

_MIGRATION_NAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")


def apply_migrations(
    connection: sqlite3.Connection,
    schema_path: str | Path | None = None,
    *,
    clock: Clock = utc_now,
) -> int:
    """Apply each available migration once and return the current version."""
    directory = Path(schema_path) if schema_path is not None else Path(__file__).with_name("schema")
    migrations = _discover_migrations(directory)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
        applied = {row["version"]: row["name"] for row in connection.execute("SELECT version, name FROM schema_migrations")}
        missing = sorted(set(applied) - set(migrations))
        if missing:
            raise MigrationError(f"previously applied migration {missing[0]:04d} is missing from '{directory}'")
        for version, (name, path) in migrations.items():
            if version in applied:
                if applied[version] != name:
                    raise MigrationError(f"migration {version:04d} name does not match recorded migration")
                continue
            script = path.read_text(encoding="utf-8")
            connection.execute("BEGIN")
            try:
                _execute_script(connection, script)
                connection.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, clock()),
                )
                connection.commit()
            except (sqlite3.Error, MigrationError):
                connection.rollback()
                raise
        row = connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()
        return int(row["version"])
    except (sqlite3.Error, OSError) as error:
        raise MigrationError(f"unable to apply database migrations: {error}") from error


def _discover_migrations(directory: Path) -> dict[int, tuple[str, Path]]:
    """Return migration files keyed by numeric version, rejecting ambiguity."""
    if not directory.is_dir():
        raise MigrationError(f"migration directory does not exist: '{directory}'")
    result: dict[int, tuple[str, Path]] = {}
    for path in sorted(directory.glob("*.sql")):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"invalid migration filename: '{path.name}'")
        version = int(match["version"])
        if version in result:
            raise MigrationError(f"duplicate migration version {version:04d}")
        result[version] = (match["name"], path)
    return result


def _execute_script(connection: sqlite3.Connection, script: str) -> None:
    """Execute a migration without ``executescript``'s implicit transaction."""
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            if statement.strip():
                try:
                    connection.execute(statement)
                except sqlite3.OperationalError as error:
                    # FTS5 is optional.  Keep the regular lore table migration
                    # usable on SQLite builds compiled without it.
                    if "CREATE VIRTUAL TABLE lore_documents_fts" not in statement or "fts5" not in str(error).lower():
                        raise
            statement = ""
    if statement.strip():
        raise MigrationError("migration ends with an incomplete SQL statement")
