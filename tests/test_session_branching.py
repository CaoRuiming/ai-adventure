"""Branch and checkpoint behavior for append-only shared histories."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_adventure.app.game_service import GameService
from local_adventure.content.loader import load_world
from local_adventure.state.events import SetFlagEvent
from local_adventure.storage.connection import open_connection
from local_adventure.storage.migrations import apply_migrations

SAMPLE_WORLD = Path(__file__).parents[1] / "worlds" / "ember_hollow"


class SessionBranchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.connection = open_connection(Path(self.temporary.name) / "game.sqlite3")
        apply_migrations(self.connection)
        ids = iter(f"id_{number}" for number in range(100))
        self.service = GameService(self.connection, load_world(SAMPLE_WORLD), id_factory=lambda: next(ids))
        self.session, _ = self.service.create_session("Original")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary.cleanup()

    def test_branch_shares_ancestor_owned_by_original_and_diverges(self) -> None:
        original_turn = self.service.commit_turn(self.session.session_id, "ask", "Mark nods.", [SetFlagEvent(type="set_flag", key="asked", value=True, reason="Question asked.")])
        branch = self.service.branch(self.session.session_id, "Alternate")
        self.assertEqual(branch.head_turn_id, original_turn.turn_id)
        branch_turn = self.service.commit_turn(branch.session_id, "leave", "You leave.", [SetFlagEvent(type="set_flag", key="left", value=True, reason="The player leaves.")])
        self.assertEqual(self.service.sessions.get(self.session.session_id).head_turn_id, original_turn.turn_id)
        self.assertEqual(self.service.sessions.get(branch.session_id).head_turn_id, branch_turn.turn_id)
        self.assertTrue(self.service.replay(branch.session_id).flags["asked"])
        self.assertTrue(self.service.replay(branch.session_id).flags["left"])
        self.assertNotIn("left", self.service.replay(self.session.session_id).flags)

    def test_checkpoint_restore_preserves_later_turn(self) -> None:
        turn = self.service.commit_turn(self.session.session_id, "ask", "Mark nods.", [SetFlagEvent(type="set_flag", key="asked", value=True, reason="Question asked.")])
        self.service.save_checkpoint(self.session.session_id, "Before leaving")
        later = self.service.commit_turn(self.session.session_id, "leave", "You leave.", [SetFlagEvent(type="set_flag", key="left", value=True, reason="The player leaves.")])
        state = self.service.restore_checkpoint(self.session.session_id, "Before leaving")
        self.assertTrue(state.flags["asked"])
        self.assertNotIn("left", state.flags)
        self.assertEqual(self.service.sessions.get(self.session.session_id).head_turn_id, turn.turn_id)
        self.assertEqual(self.service.turns.get(later.turn_id).turn_number, 2)
