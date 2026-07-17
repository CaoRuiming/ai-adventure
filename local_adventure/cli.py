"""Terminal commands and the interactive game loop."""

from __future__ import annotations

import argparse
import os
import platform
import shlex
import sqlite3
import sys
import textwrap
from pathlib import Path
from typing import Callable, TextIO

from . import __version__
from .content.loader import load_world
from .content.models import LoadedWorld
from .errors import LocalAdventureError, ModelError
from .app.game_service import GameService
from .app.turn_service import TurnService
from .context.builder import ContextAssembly
from .context.formatter import format_state
from .export.session_exporter import SessionExporter
from .llm.lm_studio import LMStudioBackend
from .paths import runtime_root
from .lore.indexer import reindex_world
from .paths import database_path
from .storage.connection import open_connection
from .storage.migrations import apply_migrations
from .storage.repositories import SessionRepository, TurnRepository, WorldRepository


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
    sessions_parser = subparsers.add_parser("sessions", help="list or create local sessions")
    sessions_subparsers = sessions_parser.add_subparsers(dest="sessions_command", required=True)
    sessions_subparsers.add_parser("list", help="list local sessions")
    create_parser = sessions_subparsers.add_parser("create", help="create a session without entering play")
    create_parser.add_argument("--world", required=True, type=Path)
    create_parser.add_argument("--scenario")
    create_parser.add_argument("--name", default="First Journey")
    play_parser = subparsers.add_parser("play", help="start or resume an interactive session")
    play_group = play_parser.add_mutually_exclusive_group(required=True)
    play_group.add_argument("--session")
    play_group.add_argument("--world", type=Path)
    play_parser.add_argument("--scenario")
    play_parser.add_argument("--name", default="First Journey")
    export_parser = subparsers.add_parser("export", help="export a session transcript and state")
    export_parser.add_argument("--session", required=True)
    export_parser.add_argument("--format", required=True, choices=("markdown", "json"))
    export_parser.add_argument("--output", required=True, type=Path)
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


def _connection():
    connection = open_connection(database_path())
    apply_migrations(connection)
    return connection


def run_sessions_list(output: TextIO | None = None) -> int:
    """Print every persisted session without loading world content."""
    output = output or sys.stdout
    connection = _connection()
    try:
        sessions = SessionRepository(connection).list_all()
    finally:
        connection.close()
    if not sessions:
        print("No sessions found.", file=output)
        return 0
    for session in sessions:
        head = "beginning" if session.head_turn_id is None else session.head_turn_id
        print(f"{session.session_id}  {session.name}  world={session.world_id}  head={head}", file=output)
    return 0


def run_sessions_create(world_path: Path, scenario_id: str | None, name: str, output: TextIO | None = None) -> int:
    """Create a session, index its lore, and print its durable ID."""
    output = output or sys.stdout
    world = load_world(world_path)
    connection = _connection()
    try:
        session, _opening = GameService(connection, world).create_session(name, scenario_id)
    finally:
        connection.close()
    print(f"Created session: {session.session_id} ({session.name})", file=output)
    return 0


def run_export(session_id: str, export_format: str, output_path: Path, output: TextIO | None = None) -> int:
    """Export a persisted session using its authored world's current display metadata."""
    output = output or sys.stdout
    connection = _connection()
    try:
        session = SessionRepository(connection).get(session_id)
        world = load_world(Path(WorldRepository(connection).source_path(session.world_id)))
        SessionExporter(connection, world).write(session_id, export_format, output_path)
    finally:
        connection.close()
    print(f"Exported {export_format}: {output_path}", file=output)
    return 0


def _wrap(text: str, output: TextIO) -> str:
    if not output.isatty():
        return text
    return "\n\n".join(textwrap.fill(paragraph) if paragraph else "" for paragraph in text.split("\n\n"))


def _print_context(context: ContextAssembly, output: TextIO) -> None:
    diagnostics = context.diagnostics
    print(f"Total characters: {diagnostics.total_chars}", file=output)
    print("Characters by section: " + ", ".join(f"{key}={value}" for key, value in diagnostics.section_chars.items()), file=output)
    print("Included lore: " + (", ".join(f"{path} ({score:.1f})" for path, score in diagnostics.lore) or "none"), file=output)
    print("Included skills: " + (", ".join(diagnostics.skill_ids) or "none"), file=output)
    print("Included turns: " + (", ".join(map(str, diagnostics.turn_numbers)) or "none"), file=output)
    print(f"Omitted: lore={diagnostics.omitted_lore_count}, skills={diagnostics.omitted_skill_count}, turns={diagnostics.omitted_turn_count}", file=output)
    print(f"Request SHA-256: {diagnostics.request_hash}", file=output)
    print(f"Raw prompts stored: {'yes' if diagnostics.raw_prompts_stored else 'no'}", file=output)


def play_game(
    *, world_path: Path | None = None, session_id: str | None = None, scenario_id: str | None = None,
    name: str = "First Journey", input_fn: Callable[[str], str] = input, output: TextIO | None = None,
) -> int:
    """Run one synchronous terminal session; all state changes stay in app services."""
    output = output or sys.stdout
    connection = _connection()
    try:
        if session_id:
            persisted = SessionRepository(connection).get(session_id)
            world = load_world(Path(WorldRepository(connection).source_path(persisted.world_id)))
            session = persisted
            opening = world.scenarios[session.scenario_id].opening_narration
        else:
            assert world_path is not None
            world = load_world(world_path)
            session, opening = GameService(connection, world).create_session(name, scenario_id)
        game = GameService(connection, world)
        turns = TurnRepository(connection)
        turn_service = TurnService(connection, world, LMStudioBackend(world.config.model.base_url))
        debug = False
        last_context: ContextAssembly | None = None
        print(world.config.title, file=output)
        print(f"Session: {session.name}", file=output)
        print(f"Model: {world.config.model.name}", file=output)
        print("Type /help for commands.\n", file=output)
        print(_wrap(opening, output), file=output)
        while True:
            try:
                line = input_fn("> ")
            except (EOFError, KeyboardInterrupt):
                print("", file=output)
                return 0
            if line.startswith("/"):
                command = line.strip()
                if command == "/quit":
                    return 0
                if command == "/help":
                    print(_HELP, file=output)
                elif command == "/state":
                    print(format_state(game.state_for_session(session.session_id)), file=output)
                elif command == "/where":
                    state = game.state_for_session(session.session_id)
                    location = state.locations[state.actors[state.player_actor_id].location_id]
                    connections = ", ".join(f"{target} ({state.locations[target].name})" for target in sorted(location.connections)) or "none"
                    print(f"{location.name} ({location.id})\nConnections: {connections}", file=output)
                elif command == "/inventory":
                    state = game.state_for_session(session.session_id)
                    items = [item for item in state.items.values() if item.holder_type == "actor" and item.holder_id == state.player_actor_id]
                    print("Inventory: " + (", ".join(f"{item.name} ({item.id})" for item in sorted(items, key=lambda item: item.id)) or "empty"), file=output)
                elif command.startswith("/history"):
                    _print_history(command, turns, session.session_id, output)
                elif command == "/context":
                    if last_context is None:
                        print("No context has been assembled yet.", file=output)
                    else:
                        _print_context(last_context, output)
                elif command == "/context full":
                    if last_context is None:
                        print("No context has been assembled yet.", file=output)
                    else:
                        try:
                            confirmation = input_fn("This may expose private game content and model instructions. Print it? [y/N] ")
                        except (EOFError, KeyboardInterrupt):
                            print("", file=output)
                            continue
                        if confirmation.casefold() == "y":
                            for message in last_context.messages:
                                print(f"{message.role.upper()}\n{message.content}\n", file=output)
                elif command == "/undo":
                    number, _state = game.undo(session.session_id)
                    print("Already at the beginning of the session." if number is None else f"Moved to turn {number}.", file=output)
                elif command.startswith("/branch "):
                    session = game.branch(session.session_id, command.removeprefix("/branch "))
                    print(f"Switched to branch: {session.name} ({session.session_id})", file=output)
                elif command.startswith("/checkpoint "):
                    game.save_checkpoint(session.session_id, command.removeprefix("/checkpoint "))
                    print("Checkpoint saved.", file=output)
                elif command.startswith("/restore "):
                    game.restore_checkpoint(session.session_id, command.removeprefix("/restore "))
                    print("Checkpoint restored.", file=output)
                elif command == "/sessions":
                    for item in SessionRepository(connection).list_for_world(world.config.id):
                        print(f"{item.session_id}  {item.name}", file=output)
                elif command == "/reload":
                    refreshed = load_world(Path(world.root))
                    changed = _entity_content_changed(world, refreshed)
                    reindex_world(connection, refreshed)
                    world = refreshed
                    game = GameService(connection, world)
                    turn_service = TurnService(connection, world, LMStudioBackend(world.config.model.base_url))
                    if changed:
                        print("Reloaded prose content. Warning: entity files changed; current session state was preserved.", file=output)
                    else:
                        print("Reloaded prose content, rules, lore, and prompt skills.", file=output)
                elif command == "/debug on":
                    debug = True
                    print("Debug diagnostics enabled.", file=output)
                elif command == "/debug off":
                    debug = False
                    print("Debug diagnostics disabled.", file=output)
                elif command == "/debug last-error":
                    if turn_service.last_error is None:
                        print("No model or validation error recorded.", file=output)
                    else:
                        print(turn_service.last_error.message, file=output)
                        for error in turn_service.last_error.validation_errors:
                            print(f"- {error}", file=output)
                elif command.startswith("/export "):
                    _run_in_game_export(command, session.session_id, connection, world, output)
                else:
                    print("Unknown command. Type /help for available commands.", file=output)
                continue
            try:
                result = turn_service.submit_turn(session.session_id, line)
            except KeyboardInterrupt:
                print("Model request cancelled; no turn was saved.", file=output)
                continue
            except LocalAdventureError as error:
                print(f"Error: {error}", file=output)
                if debug:
                    print("No state changes were committed for this action.", file=output)
                continue
            last_context = result.context
            print(_wrap(result.narration, output), file=output)
    finally:
        connection.close()


def _entity_content_changed(previous: object, refreshed: object) -> bool:
    """Compare only authored entities; prose reload must retain session state."""
    return any(getattr(previous, name) != getattr(refreshed, name) for name in ("actors", "locations", "items", "quests", "scenarios"))


def _print_history(command: str, turns: TurnRepository, session_id: str, output: TextIO) -> None:
    parts = command.split()
    if len(parts) > 2:
        print("Usage: /history [N]", file=output)
        return
    try:
        count = 5 if len(parts) == 1 else int(parts[1])
    except ValueError:
        print("Usage: /history [N]", file=output)
        return
    if not 1 <= count <= 50:
        print("History count must be between 1 and 50.", file=output)
        return
    # Session heads may share ancestry, so history must start at this head.
    connection = turns.connection
    session = SessionRepository(connection).get(session_id)
    history = turns.ancestry(session.head_turn_id)[-count:]
    if not history:
        print("No committed turns yet.", file=output)
        return
    for turn in history:
        print(f"TURN {turn.turn_number}\nPLAYER:\n{turn.player_input}\n\nNARRATOR:\n{turn.narration}", file=output)


_HELP = """Commands:
/help  /quit  /state  /where  /inventory  /history [N]
/context  /context full  /undo  /branch NAME  /checkpoint NAME  /restore NAME
/sessions  /reload  /debug on|off|last-error
/export markdown PATH  /export json PATH"""


def _run_in_game_export(command: str, session_id: str, connection: sqlite3.Connection, world: LoadedWorld, output: TextIO) -> None:
    """Parse and execute the narrow in-game export command without CLI state mutation."""
    try:
        parts = shlex.split(command)
    except ValueError:
        print("Usage: /export markdown PATH or /export json PATH", file=output)
        return
    if len(parts) != 3 or parts[1] not in {"markdown", "json"}:
        print("Usage: /export markdown PATH or /export json PATH", file=output)
        return
    try:
        SessionExporter(connection, world).write(session_id, parts[1], Path(parts[2]))
    except LocalAdventureError as error:
        print(f"Error: {error}", file=output)
        return
    print(f"Exported {parts[1]}: {parts[2]}", file=output)


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
        if args.command == "sessions":
            if args.sessions_command == "list":
                return run_sessions_list()
            return run_sessions_create(args.world, args.scenario, args.name)
        if args.command == "play":
            return play_game(world_path=args.world, session_id=args.session, scenario_id=args.scenario, name=args.name)
        if args.command == "export":
            return run_export(args.session, args.format, args.output)
    except (LocalAdventureError, ValueError) as error:
        print(f"Error: {error}")
        return 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
