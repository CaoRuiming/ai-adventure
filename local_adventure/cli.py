"""Milestone 1 command-line interface."""

from __future__ import annotations

import argparse
import os
import platform
import sqlite3
from pathlib import Path

from . import __version__
from .content.loader import load_world
from .errors import LocalAdventureError, ModelError
from .llm.lm_studio import LMStudioBackend
from .paths import runtime_root
from .lore.indexer import reindex_world
from .paths import database_path
from .storage.connection import open_connection
from .storage.migrations import apply_migrations


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser without performing any I/O."""
    parser = argparse.ArgumentParser(
        prog="python -m local_adventure",
        description="A local, open-source AI interactive fiction engine.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"local-adventure {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="check the local engine and LM Studio configuration",
    )
    doctor_parser.add_argument("--world", type=Path, help="world whose model configuration to check")
    doctor_parser.add_argument("--require-model", action="store_true", help="treat model availability as required")
    validate_parser = subparsers.add_parser(
        "validate-world",
        help="load and validate an authored world",
    )
    validate_parser.add_argument("--world", required=True, type=Path, help="path to the world directory")
    reindex_parser = subparsers.add_parser("reindex", help="index a world's Markdown lore into the local database")
    reindex_parser.add_argument("--world", required=True, type=Path, help="path to the world directory")
    return parser


def run_doctor(world_path: Path | None = None, require_model: bool = False) -> int:
    """Check local prerequisites, with model problems reported independently."""
    print("Local Adventure Doctor")
    print()
    hard_failure = False
    model_failure = False
    print(f"[PASS] Python {platform.python_version()}")
    try:
        root = runtime_root()
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        print(f"[PASS] Runtime directory writable: {root}")
    except OSError as error:
        hard_failure = True
        print(f"[FAIL] Runtime directory is not writable: {error}")
    print(f"[PASS] SQLite {sqlite3.sqlite_version}")
    try:
        connection = open_connection(database_path())
        try:
            version = apply_migrations(connection)
            fts = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'lore_documents_fts'").fetchone()
        finally:
            connection.close()
        print("[PASS] SQLite FTS5 available" if fts else "[WARN] SQLite FTS5 unavailable; fallback lore search will be used")
        print(f"[PASS] Database schema at version {version}")
    except LocalAdventureError as error:
        hard_failure = True
        print(f"[FAIL] Database initialization: {error}")
    selected_path = world_path or Path("worlds/ember_hollow")
    world = None
    try:
        world = load_world(selected_path)
        label = "Sample world" if world_path is None else "World"
        print(f"[PASS] {label} valid: {world.config.title}")
        for warning in world.warnings:
            print(f"[WARN] {warning}")
    except LocalAdventureError as error:
        hard_failure = True
        print(f"[FAIL] World validation: {error}")
    if world is not None:
        token = os.environ.get(world.config.model.api_token_env) if world.config.model.api_token_env else None
        if world.config.model.api_token_env:
            if token:
                print(f"[PASS] Configured token environment variable is present: {world.config.model.api_token_env}")
            else:
                model_failure = True
                print(f"[WARN] Configured token environment variable is absent: {world.config.model.api_token_env}")
        backend = LMStudioBackend(world.config.model.base_url)
        try:
            model_available = backend.model_is_available(world.config.model.name, world.config.model.timeout_seconds, token)
            print(f"[PASS] LM Studio reachable: {world.config.model.base_url}")
            if model_available:
                print(f"[PASS] Configured model visible: {world.config.model.name}")
            else:
                model_failure = True
                print(f"[WARN] Configured model is not visible: {world.config.model.name}")
        except ModelError:
            model_failure = True
            print(f"[WARN] LM Studio is not reachable at {world.config.model.base_url}")
            print("       Start the LM Studio local server before playing, or update world.toml.")
    print()
    if hard_failure or (require_model and model_failure):
        print("Result: local engine checks failed." if hard_failure else "Result: configured model is required but unavailable.")
        return 1
    if model_failure:
        print("Result: usable for authoring and tests; model play unavailable.")
    else:
        print("Result: local engine and configured model are available.")
    return 0


def run_validate_world(world_path: Path) -> int:
    """Validate one world and print its authored-content summary."""
    world = load_world(world_path)
    print(f"World valid: {world.config.title} ({world.config.id})")
    print(
        "Counts: "
        f"actors={len(world.actors)}, locations={len(world.locations)}, "
        f"items={len(world.items)}, quests={len(world.quests)}, "
        f"lore files={len(world.lore_documents)}, skills={len(world.skills)}"
    )
    for warning in world.warnings:
        print(f"[WARN] {warning}")
    return 0


def run_reindex(world_path: Path) -> int:
    """Load a world and incrementally synchronize its local lore index."""
    world = load_world(world_path)
    connection = open_connection(database_path())
    try:
        apply_migrations(connection)
        # Lore has a world foreign key, so persist its content identity first.
        from .storage.repositories import WorldRepository
        from .util.hashing import sha256_text
        from .util.json_tools import canonical_json
        with connection:
            WorldRepository(connection).upsert(world.config.id, world.root,
                sha256_text(canonical_json(world.model_dump(mode="json", exclude={"root", "warnings"}))), world.config.title)
        result = reindex_world(connection, world)
    finally:
        connection.close()
    mode = "FTS5" if result.fts_available else "fallback search"
    print(f"Lore index updated: indexed={result.indexed}, unchanged={result.unchanged}, removed={result.removed} ({mode})")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch the commands implemented so far."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return run_doctor(args.world, args.require_model)
        if args.command == "validate-world":
            return run_validate_world(args.world)
        if args.command == "reindex":
            return run_reindex(args.world)
    except LocalAdventureError as error:
        print(f"Error: {error}")
        return 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
