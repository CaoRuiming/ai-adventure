"""Session lifecycle operations backed by SQLite history."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable

from ..content.models import LoadedWorld
from ..errors import DatabaseError
from ..lore.indexer import reindex_world
from ..state.events import Event
from ..state.models import GameState, build_initial_state
from ..state.reducer import apply_events
from ..storage.repositories import CheckpointRepository, SessionRecord, SessionRepository, TurnRecord, TurnRepository, WorldRepository
from ..util.clocks import Clock, utc_now
from ..util.hashing import sha256_text
from ..util.json_tools import canonical_json

IdFactory = Callable[[], str]


class GameService:
    """Coordinate session creation, replay, undo, branching, and checkpoints."""

    def __init__(self, connection: sqlite3.Connection, world: LoadedWorld, *, clock: Clock = utc_now, id_factory: IdFactory | None = None) -> None:
        self.connection = connection
        self.world = world
        self.clock = clock
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))
        self.worlds = WorldRepository(connection, clock)
        self.sessions = SessionRepository(connection, clock)
        self.turns = TurnRepository(connection, clock)
        self.checkpoints = CheckpointRepository(connection, clock)

    def create_session(self, name: str, scenario_id: str | None = None) -> tuple[SessionRecord, str]:
        """Create a session and matching initial state cache."""
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 80:
            raise ValueError("session name must be between 1 and 80 characters")
        state = build_initial_state(self.world, scenario_id)
        content_hash = sha256_text(canonical_json(self.world.model_dump(mode="json", exclude={"root", "warnings"})))
        try:
            with self.connection:
                self.worlds.upsert(self.world.config.id, self.world.root, content_hash, self.world.config.title)
                reindex_world(self.connection, self.world)
                session = self.sessions.create(self._id_factory(), clean_name, state)
            return session, self.world.scenarios[state.scenario_id].opening_narration
        except sqlite3.Error as error:
            raise DatabaseError(f"unable to create session: {error}") from error

    def state_for_session(self, session_id: str) -> GameState:
        """Return a validated cache, rebuilding it from append-only history if stale."""
        session = self.sessions.get(session_id)
        cached_head, cached_state = self.sessions.cached_state(session_id)
        if cached_head == session.head_turn_id:
            return cached_state
        state = self.replay(session_id)
        with self.connection:
            self.sessions.replace_cache(session_id, session.head_turn_id, state)
        return state

    def replay(self, session_id: str) -> GameState:
        """Rebuild a session position by following parent links, including shared ancestry."""
        session = self.sessions.get(session_id)
        state = session.initial_state
        for turn in self.turns.ancestry(session.head_turn_id):
            state = apply_events(state, self.turns.events_for_turn(turn.turn_id), self.world.config.gameplay)
        return state

    def commit_turn(self, session_id: str, player_input: str, narration: str, events: list[Event]) -> TurnRecord:
        """Persist a previously validated proposal and its fully reduced state."""
        session = self.sessions.get(session_id)
        state = self.state_for_session(session_id)
        candidate = apply_events(state, events, self.world.config.gameplay)
        return self.turns.commit(session_id, session.head_turn_id, self._id_factory(), player_input, narration, events, candidate)

    def undo(self, session_id: str) -> tuple[int | None, GameState]:
        """Move the head to its parent without deleting the old turn or events."""
        session = self.sessions.get(session_id)
        if session.head_turn_id is None:
            return None, self.state_for_session(session_id)
        parent_id = self.turns.get(session.head_turn_id).parent_turn_id
        state = self._replay_to(session, parent_id)
        with self.connection:
            self.sessions.move_head(session_id, parent_id)
            self.sessions.replace_cache(session_id, parent_id, state)
        return (self.turns.get(parent_id).turn_number if parent_id else 0), state

    def branch(self, session_id: str, name: str) -> SessionRecord:
        """Create a new session with the same immutable history and current state."""
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 80:
            raise ValueError("branch name must be between 1 and 80 characters")
        source = self.sessions.get(session_id)
        state = self.state_for_session(session_id)
        now = self.clock()
        branch_id = self._id_factory()
        try:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO sessions (session_id, name, world_id, scenario_id, head_turn_id, initial_state_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (branch_id, clean_name, source.world_id, source.scenario_id, source.head_turn_id, source.initial_state.canonical_json(), now, now),
                )
                self.connection.execute(
                    "INSERT INTO state_cache (session_id, head_turn_id, state_json, updated_at) VALUES (?, ?, ?, ?)",
                    (branch_id, source.head_turn_id, state.canonical_json(), now),
                )
            return self.sessions.get(branch_id)
        except sqlite3.Error as error:
            raise DatabaseError(f"unable to branch session: {error}") from error

    def save_checkpoint(self, session_id: str, name: str) -> None:
        """Save or replace a named checkpoint at the current session head."""
        if not name.strip() or len(name) > 80:
            raise ValueError("checkpoint name must be between 1 and 80 characters")
        session = self.sessions.get(session_id)
        with self.connection:
            self.checkpoints.save(self._id_factory(), session_id, name.strip(), session.head_turn_id)

    def restore_checkpoint(self, session_id: str, name: str) -> GameState:
        """Move a session head to a named checkpoint while retaining later history."""
        session = self.sessions.get(session_id)
        checkpoint = self.checkpoints.get(session_id, name)
        state = self._replay_to(session, checkpoint.turn_id)
        with self.connection:
            self.sessions.move_head(session_id, checkpoint.turn_id)
            self.sessions.replace_cache(session_id, checkpoint.turn_id, state)
        return state

    def _replay_to(self, session: SessionRecord, head_turn_id: str | None) -> GameState:
        state = session.initial_state
        for turn in self.turns.ancestry(head_turn_id):
            state = apply_events(state, self.turns.events_for_turn(turn.turn_id), self.world.config.gameplay)
        return state
