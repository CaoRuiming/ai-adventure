"""Clock helpers used by storage and application services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

Clock = Callable[[], str]


def utc_now() -> str:
    """Return the current UTC timestamp in the engine's storage format."""
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
