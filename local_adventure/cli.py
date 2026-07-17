"""Milestone 1 command-line interface."""

from __future__ import annotations

import argparse
import platform

from . import __version__


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


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch the commands implemented so far."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return run_doctor()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
