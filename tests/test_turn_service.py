"""Offline turn-lifecycle coverage using the deterministic scripted backend."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_adventure.app.game_service import GameService
from local_adventure.app.turn_service import TurnService
from local_adventure.content.loader import load_world
from local_adventure.errors import ProposalValidationError
from local_adventure.llm.scripted import ScriptedModelBackend
from local_adventure.storage.connection import open_connection
from local_adventure.storage.migrations import apply_migrations

SAMPLE_WORLD = Path(__file__).parents[1] / "worlds" / "ember_hollow"
NOW = "2026-07-16T00:00:00.000000Z"


class TurnServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.connection = open_connection(Path(self.temporary.name) / "game.sqlite3")
        apply_migrations(self.connection, clock=lambda: NOW)
        self.world = load_world(SAMPLE_WORLD)
        self.ids = iter(f"id_{number}" for number in range(200))
        self.game = GameService(self.connection, self.world, clock=lambda: NOW, id_factory=lambda: next(self.ids))
        self.session, _ = self.game.create_session("Turn Test")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary.cleanup()

    def test_valid_proposal_commits_only_after_validation_and_replay_matches_cache(self) -> None:
        backend = ScriptedModelBackend(['{"narration":"Mark gives you the key.","events":[{"type":"transfer_item","item_id":"brass_key","holder_type":"actor","holder_id":"player","reason":"Mark entrusts the key to you."}]}'])
        service = self._turn_service(backend)

        result = service.submit_turn(self.session.session_id, "I ask for the key.\n")

        self.assertEqual(result.turn.turn_number, 1)
        self.assertEqual(result.narration, "Mark gives you the key.")
        self.assertEqual(self.game.state_for_session(self.session.session_id), self.game.replay(self.session.session_id))
        self.assertEqual(self.game.state_for_session(self.session.session_id).items["brass_key"].holder_id, "player")
        row = self.connection.execute("SELECT model_call_id FROM turns WHERE turn_id = ?", (result.turn.turn_id,)).fetchone()
        self.assertIsNotNone(row["model_call_id"])

    def test_invalid_first_output_and_valid_repair_create_one_committed_turn(self) -> None:
        backend = ScriptedModelBackend([
            '{"narration":"Bad move.","events":[{"type":"move_actor","actor_id":"player","location_id":"missing","reason":"Bad destination."}]}',
            '{"narration":"Mark considers your request.","events":[]}',
        ])
        service = self._turn_service(backend)

        result = service.submit_turn(self.session.session_id, "I ask Mark for help.")

        self.assertEqual(result.turn.turn_number, 1)
        self.assertEqual(len(backend.requests), 2)
        self.assertEqual(backend.requests[1].temperature, 0.2)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0], 1)
        calls = self.connection.execute("SELECT attempt_number, validation_errors_json FROM model_calls ORDER BY attempt_number").fetchall()
        self.assertEqual([row["attempt_number"] for row in calls], [1, 2])
        self.assertIsNotNone(calls[0]["validation_errors_json"])
        self.assertIsNone(calls[1]["validation_errors_json"])
        self.assertIn("move_actor.location_id 'missing' does not exist", backend.requests[1].messages[1].content)
        self.assertIn("ORIGINAL INVALID RESPONSE", backend.requests[1].messages[1].content)

    def test_safe_noop_events_commit_without_using_repair(self) -> None:
        backend = ScriptedModelBackend([
            '{"narration":"You pause at the observatory.","events":[{"type":"move_actor","actor_id":"player","location_id":"observatory","reason":"The player stays put."},{"type":"transfer_item","item_id":"brass_key","holder_type":"actor","holder_id":"mark","reason":"The key remains with Mark."}]}'
        ])
        service = self._turn_service(backend)

        result = service.submit_turn(self.session.session_id, "I pause.")

        self.assertEqual(result.turn.turn_number, 1)
        self.assertEqual(len(backend.requests), 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM state_events").fetchone()[0], 0)
        self.assertEqual(self.game.state_for_session(self.session.session_id), self.game.replay(self.session.session_id))

    def test_failed_repair_leaves_head_unchanged_and_retains_last_error(self) -> None:
        backend = ScriptedModelBackend(["not json", "still not json"])
        service = self._turn_service(backend)

        with self.assertRaisesRegex(ProposalValidationError, "no turn was saved"):
            service.submit_turn(self.session.session_id, "I wait.")

        self.assertIsNone(self.game.sessions.get(self.session.session_id).head_turn_id)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0], 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM state_events").fetchone()[0], 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0], 2)
        self.assertIsNotNone(service.last_error)

    def test_every_tenth_committed_turn_creates_bounded_extractive_summary(self) -> None:
        backend = ScriptedModelBackend(['{"narration":"A quiet moment.","events":[]}'] * 10)
        service = self._turn_service(backend)
        for number in range(10):
            service.submit_turn(self.session.session_id, f"I wait {number}.")
            self.assertEqual(self.game.state_for_session(self.session.session_id), self.game.replay(self.session.session_id))

        row = self.connection.execute("SELECT content, through_turn_id FROM summaries WHERE session_id = ?", (self.session.session_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertTrue(row["content"].startswith("EXTRACTIVE SCENE SUMMARY"))
        self.assertLessEqual(len(row["content"]), 12_000)
        self.assertEqual(row["through_turn_id"], self.game.sessions.get(self.session.session_id).head_turn_id)

    def _turn_service(self, backend: ScriptedModelBackend) -> TurnService:
        return TurnService(self.connection, self.world, backend, clock=lambda: NOW, id_factory=lambda: next(self.ids))


if __name__ == "__main__":
    unittest.main()
