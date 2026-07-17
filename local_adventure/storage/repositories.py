"""Explicit repositories for the SQLite runtime store."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from ..errors import CheckpointNotFoundError, ConcurrentSessionUpdateError, DatabaseError, SessionNotFoundError
from ..state.events import Event, parse_event
from ..state.models import GameState
from ..util.clocks import Clock, utc_now
from ..util.json_tools import canonical_json

if False:  # pragma: no cover - imports only for static type checkers
    from ..lore.models import IndexedLoreDocument, StoredLoreDocument


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    name: str
    world_id: str
    scenario_id: str
    head_turn_id: str | None
    initial_state: GameState
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TurnRecord:
    turn_id: str
    session_id: str
    parent_turn_id: str | None
    turn_number: int
    player_input: str
    narration: str
    status: str
    created_at: str


@dataclass(frozen=True)
class CheckpointRecord:
    checkpoint_id: str
    session_id: str
    turn_id: str | None
    name: str
    created_at: str


class WorldRepository:
    """Persist loaded-world identity data without owning content loading."""

    def __init__(self, connection: sqlite3.Connection, clock: Clock = utc_now) -> None:
        self.connection, self.clock = connection, clock

    def upsert(self, world_id: str, source_path: str, content_hash: str, title: str) -> None:
        self.connection.execute(
            "INSERT INTO worlds (world_id, source_path, content_hash, title, loaded_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(world_id) DO UPDATE SET source_path=excluded.source_path, content_hash=excluded.content_hash, title=excluded.title, loaded_at=excluded.loaded_at",
            (world_id, source_path, content_hash, title, self.clock()),
        )


class SessionRepository:
    """Create, fetch, and administratively move session heads."""

    def __init__(self, connection: sqlite3.Connection, clock: Clock = utc_now) -> None:
        self.connection, self.clock = connection, clock

    def create(self, session_id: str, name: str, state: GameState) -> SessionRecord:
        now = self.clock()
        initial_json = state.canonical_json()
        self.connection.execute(
            "INSERT INTO sessions (session_id, name, world_id, scenario_id, head_turn_id, initial_state_json, created_at, updated_at) VALUES (?, ?, ?, ?, NULL, ?, ?, ?)",
            (session_id, name, state.world_id, state.scenario_id, initial_json, now, now),
        )
        self.connection.execute(
            "INSERT INTO state_cache (session_id, head_turn_id, state_json, updated_at) VALUES (?, NULL, ?, ?)",
            (session_id, initial_json, now),
        )
        return self.get(session_id)

    def get(self, session_id: str) -> SessionRecord:
        row = self.connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            raise SessionNotFoundError(f"session '{session_id}' does not exist")
        return _session_from_row(row)

    def list_for_world(self, world_id: str) -> list[SessionRecord]:
        rows = self.connection.execute("SELECT * FROM sessions WHERE world_id = ? ORDER BY created_at, session_id", (world_id,)).fetchall()
        return [_session_from_row(row) for row in rows]

    def cached_state(self, session_id: str) -> tuple[str | None, GameState]:
        row = self.connection.execute("SELECT head_turn_id, state_json FROM state_cache WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            raise DatabaseError(f"state cache for session '{session_id}' does not exist")
        return row["head_turn_id"], GameState.model_validate_json(row["state_json"])

    def replace_cache(self, session_id: str, head_turn_id: str | None, state: GameState) -> None:
        cursor = self.connection.execute(
            "UPDATE state_cache SET head_turn_id = ?, state_json = ?, updated_at = ? WHERE session_id = ?",
            (head_turn_id, state.canonical_json(), self.clock(), session_id),
        )
        if cursor.rowcount != 1:
            raise DatabaseError(f"state cache for session '{session_id}' does not exist")

    def move_head(self, session_id: str, head_turn_id: str | None) -> None:
        cursor = self.connection.execute("UPDATE sessions SET head_turn_id = ?, updated_at = ? WHERE session_id = ?", (head_turn_id, self.clock(), session_id))
        if cursor.rowcount != 1:
            raise SessionNotFoundError(f"session '{session_id}' does not exist")


class TurnRepository:
    """Append and traverse turn/event history."""

    def __init__(self, connection: sqlite3.Connection, clock: Clock = utc_now) -> None:
        self.connection, self.clock = connection, clock

    def get(self, turn_id: str) -> TurnRecord:
        row = self.connection.execute("SELECT * FROM turns WHERE turn_id = ?", (turn_id,)).fetchone()
        if row is None:
            raise DatabaseError(f"turn '{turn_id}' does not exist")
        return _turn_from_row(row)

    def events_for_turn(self, turn_id: str) -> list[Event]:
        rows = self.connection.execute("SELECT payload_json FROM state_events WHERE turn_id = ? ORDER BY sequence_number", (turn_id,)).fetchall()
        return [parse_event(json.loads(row["payload_json"])) for row in rows]

    def ancestry(self, head_turn_id: str | None) -> list[TurnRecord]:
        result: list[TurnRecord] = []
        current = head_turn_id
        while current is not None:
            turn = self.get(current)
            result.append(turn)
            current = turn.parent_turn_id
        result.reverse()
        return result

    def commit(
        self, session_id: str, expected_parent_id: str | None, turn_id: str, player_input: str,
        narration: str, events: list[Event], state: GameState,
    ) -> TurnRecord:
        """Atomically append a turn if the session head is unchanged."""
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute("SELECT head_turn_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if row is None:
                raise SessionNotFoundError(f"session '{session_id}' does not exist")
            if row["head_turn_id"] != expected_parent_id:
                raise ConcurrentSessionUpdateError("session head changed before turn could be committed")
            number = 1 if expected_parent_id is None else self.get(expected_parent_id).turn_number + 1
            now = self.clock()
            self.connection.execute(
                "INSERT INTO turns (turn_id, session_id, parent_turn_id, turn_number, player_input, narration, status, model_call_id, created_at) VALUES (?, ?, ?, ?, ?, ?, 'committed', NULL, ?)",
                (turn_id, session_id, expected_parent_id, number, player_input, narration, now),
            )
            for sequence, event in enumerate(events):
                self.connection.execute(
                    "INSERT INTO state_events (event_id, turn_id, sequence_number, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (f"{turn_id}:{sequence}", turn_id, sequence, event.type, canonical_json(event.model_dump(mode="json")), now),
                )
            self.connection.execute("UPDATE state_cache SET head_turn_id = ?, state_json = ?, updated_at = ? WHERE session_id = ?", (turn_id, state.canonical_json(), now, session_id))
            self.connection.execute("UPDATE sessions SET head_turn_id = ?, updated_at = ? WHERE session_id = ?", (turn_id, now, session_id))
            self.connection.commit()
            return self.get(turn_id)
        except (DatabaseError, SessionNotFoundError, ConcurrentSessionUpdateError):
            self.connection.rollback()
            raise
        except sqlite3.Error as error:
            self.connection.rollback()
            raise DatabaseError(f"unable to commit turn: {error}") from error


class CheckpointRepository:
    """Store named, non-destructive references to session heads."""

    def __init__(self, connection: sqlite3.Connection, clock: Clock = utc_now) -> None:
        self.connection, self.clock = connection, clock

    def save(self, checkpoint_id: str, session_id: str, name: str, turn_id: str | None) -> CheckpointRecord:
        self.connection.execute(
            "INSERT INTO named_checkpoints (checkpoint_id, session_id, turn_id, name, created_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, name) DO UPDATE SET turn_id=excluded.turn_id, created_at=excluded.created_at",
            (checkpoint_id, session_id, turn_id, name, self.clock()),
        )
        return self.get(session_id, name)

    def get(self, session_id: str, name: str) -> CheckpointRecord:
        row = self.connection.execute("SELECT * FROM named_checkpoints WHERE session_id = ? AND name = ?", (session_id, name)).fetchone()
        if row is None:
            raise CheckpointNotFoundError(f"checkpoint '{name}' does not exist for this session")
        return CheckpointRecord(**dict(row))


class ModelCallRepository:
    """Reserved model-call audit repository; model integration is Milestone 6."""


class LoreRepository:
    """Persist and query lore documents; retrieval policy belongs in ``lore``."""

    def __init__(self, connection: sqlite3.Connection, clock: Clock = utc_now) -> None:
        self.connection, self.clock = connection, clock

    def fts_available(self) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'lore_documents_fts'"
        ).fetchone()
        return row is not None

    def existing_hashes(self, world_id: str) -> dict[str, str]:
        rows = self.connection.execute(
            "SELECT relative_path, content_hash FROM lore_documents WHERE world_id = ?", (world_id,)
        ).fetchall()
        return {row["relative_path"]: row["content_hash"] for row in rows}

    def upsert(self, document: "IndexedLoreDocument") -> None:
        metadata_json = canonical_json(document.metadata)
        previous = self.connection.execute(
            "SELECT document_id FROM lore_documents WHERE world_id = ? AND relative_path = ?",
            (document.world_id, document.relative_path),
        ).fetchone()
        if self.fts_available() and previous is not None:
            self.connection.execute(
                "DELETE FROM lore_documents_fts WHERE world_id = ? AND document_id = ?",
                (document.world_id, previous["document_id"]),
            )
        self.connection.execute(
            "INSERT INTO lore_documents (document_id, world_id, relative_path, title, kind, metadata_json, body, content_hash, modified_ns, indexed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(world_id, relative_path) DO UPDATE SET document_id=excluded.document_id, title=excluded.title, kind=excluded.kind, metadata_json=excluded.metadata_json, body=excluded.body, content_hash=excluded.content_hash, modified_ns=excluded.modified_ns, indexed_at=excluded.indexed_at",
            (document.document_id, document.world_id, document.relative_path, document.title, document.kind,
             metadata_json, document.body, document.content_hash, document.modified_ns, self.clock()),
        )
        if self.fts_available():
            self.connection.execute("DELETE FROM lore_documents_fts WHERE world_id = ? AND document_id = ?", (document.world_id, document.document_id))
            self.connection.execute(
                "INSERT INTO lore_documents_fts (document_id, world_id, title, aliases, tags, body) VALUES (?, ?, ?, ?, ?, ?)",
                (document.document_id, document.world_id, document.title, " ".join(document.metadata.get("aliases", [])),
                 " ".join(document.metadata.get("tags", [])), document.body),
            )

    def remove_missing(self, world_id: str, relative_paths: set[str]) -> int:
        rows = self.connection.execute("SELECT document_id, relative_path FROM lore_documents WHERE world_id = ?", (world_id,)).fetchall()
        missing = [row for row in rows if row["relative_path"] not in relative_paths]
        for row in missing:
            if self.fts_available():
                self.connection.execute("DELETE FROM lore_documents_fts WHERE world_id = ? AND document_id = ?", (world_id, row["document_id"]))
            self.connection.execute("DELETE FROM lore_documents WHERE document_id = ?", (row["document_id"],))
        return len(missing)

    def documents(self, world_id: str) -> list["StoredLoreDocument"]:
        rows = self.connection.execute("SELECT * FROM lore_documents WHERE world_id = ? ORDER BY document_id", (world_id,)).fetchall()
        return [_lore_from_row(row) for row in rows]

    def fts_candidates(self, world_id: str, query: str) -> dict[str, float]:
        if not self.fts_available() or not query:
            return {}
        try:
            rows = self.connection.execute(
                "SELECT document_id, bm25(lore_documents_fts) AS rank FROM lore_documents_fts WHERE world_id = ? AND lore_documents_fts MATCH ? LIMIT 30",
                (world_id, query),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        # bm25 ranks are negative, with a lower value being more relevant.
        return {row["document_id"]: -float(row["rank"]) for row in rows}


class SummaryRepository:
    """Reserved summary repository; summaries are not implemented yet."""


def _lore_from_row(row: sqlite3.Row) -> "StoredLoreDocument":
    from ..lore.models import StoredLoreDocument
    return StoredLoreDocument(
        document_id=row["document_id"], world_id=row["world_id"], relative_path=row["relative_path"],
        title=row["title"], kind=row["kind"], metadata=json.loads(row["metadata_json"]), body=row["body"],
        content_hash=row["content_hash"], modified_ns=row["modified_ns"],
    )


def _session_from_row(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        session_id=row["session_id"], name=row["name"], world_id=row["world_id"], scenario_id=row["scenario_id"],
        head_turn_id=row["head_turn_id"], initial_state=GameState.model_validate_json(row["initial_state_json"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _turn_from_row(row: sqlite3.Row) -> TurnRecord:
    return TurnRecord(
        turn_id=row["turn_id"], session_id=row["session_id"], parent_turn_id=row["parent_turn_id"],
        turn_number=row["turn_number"], player_input=row["player_input"], narration=row["narration"],
        status=row["status"], created_at=row["created_at"],
    )
