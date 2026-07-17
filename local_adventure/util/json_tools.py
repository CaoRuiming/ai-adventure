"""Canonical JSON helpers for stable storage and hashing."""

from __future__ import annotations

import json


def canonical_json(value: object) -> str:
    """Serialize JSON-compatible data in a stable, compact representation."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
