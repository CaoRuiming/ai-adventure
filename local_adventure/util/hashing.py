"""SHA-256 helpers for canonical engine data."""

from __future__ import annotations

import hashlib


def sha256_text(value: str) -> str:
    """Return the lowercase SHA-256 hexadecimal digest of UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
