"""Stable formatting primitives for context sections."""

from __future__ import annotations

import json

from ..lore.models import LoreMatch
from ..state.events import Event
from ..state.models import state_projection
from ..storage.repositories import TurnRecord


def format_state(state: object) -> str:
    return "CURRENT STATE\n" + json.dumps(state_projection(state), ensure_ascii=False, sort_keys=True, indent=2)


def format_lore(match: LoreMatch, maximum_chars: int) -> str:
    prefix = f"--- LORE: {match.document.title} [{match.document.relative_path}] ---\n"
    suffix = "\n--- END LORE ---"
    return prefix + truncate_paragraphs(match.document.body, max(0, maximum_chars - len(prefix) - len(suffix))) + suffix


def format_turn(turn: TurnRecord, events: list[Event], maximum_chars: int) -> str:
    header = f"TURN {turn.turn_number}\nPLAYER:\n{turn.player_input}\n\nNARRATOR:\n"
    event_lines = "\n\nSTATE EVENTS:\n" + "\n".join(f"- {event.type}: {event.reason}" for event in events)
    return header + truncate_paragraphs(turn.narration, max(0, maximum_chars - len(header) - len(event_lines))) + event_lines


def truncate_paragraphs(text: str, maximum_chars: int) -> str:
    """Trim at paragraph boundaries; use a final character slice only when needed."""
    if len(text) <= maximum_chars:
        return text
    if maximum_chars <= 0:
        return ""
    result = ""
    for paragraph in text.split("\n\n"):
        candidate = paragraph if not result else result + "\n\n" + paragraph
        if len(candidate) > maximum_chars:
            break
        result = candidate
    return result if result else text[:maximum_chars]
