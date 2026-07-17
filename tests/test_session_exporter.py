"""Offline export and release-flow coverage."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from local_adventure.app.game_service import GameService
from local_adventure.app.turn_service import TurnService
from local_adventure.content.loader import load_world
from local_adventure.errors import ConfigurationError
from local_adventure.export.session_exporter import SessionExporter
from local_adventure.llm.scripted import ScriptedModelBackend
from local_adventure.storage.connection import open_connection
from local_adventure.storage.migrations import apply_migrations

SAMPLE_WORLD = Path(__file__).parents[1] / "worlds" / "ember_hollow"
NOW = "2026-07-17T00:00:00.000000Z"


class SessionExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.connection = open_connection(Path(self.temporary.name) / "game.sqlite3")
        apply_migrations(self.connection, clock=lambda: NOW)
        self.world = load_world(SAMPLE_WORLD)
        self.ids = iter(f"id_{number}" for number in range(100))
        self.game = GameService(self.connection, self.world, clock=lambda: NOW, id_factory=lambda: next(self.ids))
        self.session, _ = self.game.create_session("Release Test")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary.cleanup()

    def test_markdown_and_json_exports_are_safe_and_exclude_audits(self) -> None:
        self._commit_two_turns(self.session.session_id)
        self.game.save_checkpoint(self.session.session_id, "At Gate")
        exporter = SessionExporter(self.connection, self.world)

        markdown = exporter.render_markdown(self.session.session_id).content
        payload = json.loads(exporter.render_json(self.session.session_id).content)

        self.assertIn("# Release Test", markdown)
        self.assertIn("## Turn 2", markdown)
        self.assertIn("> ## Player-controlled heading", markdown)
        self.assertIn("Brass Key was transferred to Traveler.", markdown)
        self.assertEqual(payload["export_schema_version"], 1)
        self.assertEqual(len(payload["turns"]), 2)
        self.assertEqual(payload["current_state"]["actors"]["player"]["location_id"], "west_gate")
        self.assertEqual(payload["checkpoints"][0]["name"], "At Gate")
        self.assertNotIn("model_calls", payload)
        self.assertNotIn("raw_response", exporter.render_json(self.session.session_id).content)

    def test_end_to_end_scripted_history_undo_branch_and_export(self) -> None:
        self._commit_two_turns(self.session.session_id)
        self.game.undo(self.session.session_id)
        branch = self.game.branch(self.session.session_id, "Alternate Choice")
        branch_backend = ScriptedModelBackend(['{"narration":"You wait beside the gate.","events":[]}'])
        TurnService(self.connection, self.world, branch_backend, clock=lambda: NOW, id_factory=lambda: next(self.ids)).submit_turn(branch.session_id, "I wait.")

        exporter = SessionExporter(self.connection, self.world)
        original = json.loads(exporter.render_json(self.session.session_id).content)
        branched = json.loads(exporter.render_json(branch.session_id).content)

        self.assertEqual(len(original["turns"]), 1)
        self.assertEqual(len(branched["turns"]), 2)
        self.assertNotEqual(original["session"]["head_turn_id"], branched["session"]["head_turn_id"])
        self.assertEqual(original["current_state"]["items"]["brass_key"]["holder_id"], "player")

    def test_write_rejects_a_directory_target(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "export path is a directory"):
            SessionExporter(self.connection, self.world).write(self.session.session_id, "json", Path(self.temporary.name))

    def _commit_two_turns(self, session_id: str) -> None:
        backend = ScriptedModelBackend([
            '{"narration":"Mark gives you the key.\\n\\n## Player-controlled heading","events":[{"type":"transfer_item","item_id":"brass_key","holder_type":"actor","holder_id":"player","reason":"Mark trusts you with it."},{"type":"adjust_relationship","source_actor_id":"mark","target_actor_id":"player","dimension":"trust","delta":2,"reason":"Your promise reassures Mark."}]}',
            '{"narration":"You reach the west gate.","events":[{"type":"move_actor","actor_id":"player","location_id":"west_gate","reason":"You walk along the marked path."}]}',
        ])
        service = TurnService(self.connection, self.world, backend, clock=lambda: NOW, id_factory=lambda: next(self.ids))
        service.submit_turn(session_id, "I promise to keep her secret and ask for the key.")
        service.submit_turn(session_id, "I walk to the west gate.")


if __name__ == "__main__":
    unittest.main()
