"""Typed values exchanged by lore indexing and retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexedLoreDocument:
    document_id: str
    world_id: str
    relative_path: str
    title: str
    kind: str
    metadata: dict[str, object]
    body: str
    content_hash: str
    modified_ns: int


@dataclass(frozen=True)
class StoredLoreDocument:
    document_id: str
    world_id: str
    relative_path: str
    title: str
    kind: str
    metadata: dict[str, object]
    body: str
    content_hash: str
    modified_ns: int


@dataclass(frozen=True)
class LoreMatch:
    document: StoredLoreDocument
    score: float
