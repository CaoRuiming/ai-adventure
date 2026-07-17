"""Milestone 1 command-line interface."""

from __future__ import annotations

import argparse
import platform
from pathlib import Path

from . import __version__
from .content.loader import load_world
from .errors import LocalAdventureError


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
    subparsers.add_parser(
        "doctor",
        help="run the Milestone 1 environment diagnostic placeholder",
    )
    validate_parser = subparsers.add_parser(
        "validate-world",
        help="load and validate an authored world",
    )
    validate_parser.add_argument("--world", required=True, type=Path, help="path to the world directory")
    return parser


def run_doctor() -> int:
    """Print the Milestone 1 diagnostic placeholder."""
    version = platform.python_version()
    print("Local Adventure Doctor")
    print()
    print(f"[PASS] Python {version}")
    print("[INFO] Full environment checks will be added in a later milestone.")
    print()
    print("Result: Milestone 1 repository skeleton is available.")
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


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch the commands implemented so far."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return run_doctor()
        if args.command == "validate-world":
            return run_validate_world(args.world)
    except LocalAdventureError as error:
        print(f"Error: {error}")
        return 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
