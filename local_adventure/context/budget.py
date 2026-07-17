"""Small helpers for exact character-count context budgets."""

from __future__ import annotations


def join_sections(sections: list[str]) -> str:
    return "\n\n".join(section for section in sections if section)


def within_budget(text: str, maximum_chars: int) -> bool:
    return len(text) <= maximum_chars
