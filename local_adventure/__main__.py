"""Module entry point for ``python -m local_adventure``."""

from __future__ import annotations

import sys


MINIMUM_PYTHON = (3, 12)


def _check_python_version() -> int | None:
    """Return an exit code when the interpreter is unsupported."""
    if sys.version_info < MINIMUM_PYTHON:
        required = ".".join(str(part) for part in MINIMUM_PYTHON)
        detected = ".".join(str(part) for part in sys.version_info[:3])
        print(
            f"Local Adventure Engine requires Python {required} or newer; "
            f"detected Python {detected}.",
            file=sys.stderr,
        )
        return 1
    return None


def main() -> int:
    """Run the command-line application after checking Python support."""
    version_error = _check_python_version()
    if version_error is not None:
        return version_error

    from .cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
