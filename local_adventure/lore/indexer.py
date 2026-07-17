"""Safe, incremental indexing of authored lore into SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..content.frontmatter import read_lore_document
from ..content.models import LoadedWorld
from ..errors import ContentParseError, WorldValidationError
from ..storage.repositories import LoreRepository
from ..util.hashing import sha256_text
from .models import IndexedLoreDocument


@dataclass(frozen=True)
class ReindexResult:
    indexed: int
    unchanged: int
    removed: int
    fts_available: bool


def reindex_world(connection: sqlite3.Connection, world: LoadedWorld) -> ReindexResult:
    """Synchronize one world's lore files and FTS rows in one transaction."""
    root = Path(world.root)
    paths = _lore_paths(root)
    repository = LoreRepository(connection)
    existing = repository.existing_hashes(world.config.id)
    indexed = unchanged = 0
    with connection:
        for path in paths:
            relative_path = path.relative_to(root).as_posix()
            normalized = _normalized_file(path)
            content_hash = sha256_text(normalized)
            if existing.get(relative_path) == content_hash:
                unchanged += 1
                continue
            parsed = read_lore_document(path, relative_path)
            repository.upsert(IndexedLoreDocument(
                document_id=parsed.metadata.id, world_id=world.config.id, relative_path=relative_path,
                title=parsed.metadata.title, kind=parsed.metadata.kind,
                metadata=parsed.metadata.model_dump(mode="json"), body=parsed.body,
                content_hash=content_hash, modified_ns=path.stat().st_mtime_ns,
            ))
            indexed += 1
        removed = repository.remove_missing(world.config.id, {path.relative_to(root).as_posix() for path in paths})
    return ReindexResult(indexed, unchanged, removed, repository.fts_available())


def _lore_paths(root: Path) -> list[Path]:
    directory = root / "lore"
    if not directory.exists():
        return []
    _ensure_inside(root, directory)
    paths: list[Path] = []
    for path in directory.rglob("*.md"):
        _ensure_inside(root, path)
        if path.is_file():
            paths.append(path)
    return sorted(paths, key=lambda value: value.relative_to(root).as_posix())


def _normalized_file(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ContentParseError(f"{path}: file exceeds 1 MiB limit")
    try:
        return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as error:
        raise ContentParseError(f"{path}: file must be UTF-8") from error


def _ensure_inside(root: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise WorldValidationError(f"{path}: path escapes selected world root") from error
