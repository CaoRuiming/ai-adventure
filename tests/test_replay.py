"""Replay tests for cached authoritative session state."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_adventure.app.game_service import GameService
from local_adventure.content.loader import load_world
from local_adventure.state.events import SetFlagEvent, TransferItemEvent
from local_adventure.storage.connection import open_connection
from local_adventure.storage.migrations import apply_migrations

SAMPLE_WORLD = Path(__file__).parents[1] / "worlds" / "ember_hollow"


class ReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.connection = open_connection(Path(self.temporary.name) / "game.sqlite3")
        apply_migrations(self.connection)
        ids = iter(f"id_{number}" for number in range(100))
        self.service = GameService(self.connection, load_world(SAMPLE_WORLD), id_factory=lambda: next(ids))
        self.session, _ = self.service.create_session("Replay Test")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary.cleanup()

    def test_replay_zero_turns_equals_initial_state(self) -> None:
        self.assertEqual(self.service.replay(self.session.session_id), self.service.state_for_session(self.session.session_id))

    def test_replay_matches_cache_after_several_turns(self) -> None:
        self.service.commit_turn(self.session.session_id, "ask", "Mark nods.", [SetFlagEvent(type="set_flag", key="asked", value=True, reason="Question asked.")])
        self.service.commit_turn(self.session.session_id, "take", "Mark gives the key.", [TransferItemEvent(type="transfer_item", item_id="brass_key", holder_type="actor", holder_id="player", reason="The key is given.")])
        self.assertEqual(self.service.replay(self.session.session_id).canonical_json(), self.service.state_for_session(self.session.session_id).canonical_json())

    def test_undo_rebuilds_cache_without_deleting_history(self) -> None:
        first = self.service.commit_turn(self.session.session_id, "ask", "Mark nods.", [SetFlagEvent(type="set_flag", key="asked", value=True, reason="Question asked.")])
        second = self.service.commit_turn(self.session.session_id, "take", "Mark gives the key.", [TransferItemEvent(type="transfer_item", item_id="brass_key", holder_type="actor", holder_id="player", reason="The key is given.")])
        number, state = self.service.undo(self.session.session_id)
        self.assertEqual(number, 1)
        self.assertEqual(state.items["brass_key"].holder_id, "mark")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0], 2)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM state_events").fetchone()[0], 2)
        self.assertEqual(self.service.sessions.get(self.session.session_id).head_turn_id, first.turn_id)
        self.assertEqual(self.service.turns.get(second.turn_id).turn_number, 2)
