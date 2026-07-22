"""Offline turn-lifecycle coverage using the deterministic scripted backend."""

from __future__ import annotations

import tempfile
import unittest
import shutil
from pathlib import Path

from local_adventure.app.game_service import GameService
from local_adventure.app.turn_service import TurnService
from local_adventure.content.loader import load_world
from local_adventure.errors import ProposalValidationError
from local_adventure.llm.backend import ModelResponse
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

    def test_continue_turn_prompts_for_an_autoplay_scene_beat_and_commits_it(self) -> None:
        backend = ScriptedModelBackend([
            '{"narration":"Mark studies the rain-dark path and grows more trusting.","events":['
            '{"type":"adjust_relationship","source_actor_id":"mark","target_actor_id":"player",'
            '"dimension":"trust","delta":1,"reason":"Mark is reassured by the quiet moment."}]}'
        ])
        service = self._turn_service(backend)

        result = service.continue_turn(self.session.session_id)

        self.assertEqual(result.turn.turn_number, 1)
        self.assertEqual(result.turn.player_input, "/continue")
        self.assertEqual(self.game.state_for_session(self.session.session_id).actors["mark"].relationships["player"]["trust"], 1)
        prompt = backend.requests[0].messages[1].content
        self.assertIn("AUTOPLAY CONTINUATION", prompt)
        self.assertIn("without waiting for player input", prompt)
        self.assertIn("Do not\nchoose actions", prompt)
        self.assertIn("Treat the IMMEDIATE PREVIOUS BEAT", prompt)

    def test_continue_includes_the_prior_beat_and_full_validated_events(self) -> None:
        backend = ScriptedModelBackend([
            '{"narration":"Mark offers the brass key, then waits for your answer.","events":['
            '{"type":"transfer_item","item_id":"brass_key","holder_type":"actor","holder_id":"player","reason":"Mark entrusts the key to you."}]}',
            '{"narration":"Rain taps the key as Mark watches your choice.","events":[]}',
        ])
        service = self._turn_service(backend)

        service.submit_turn(self.session.session_id, "I ask Mark for the key.")
        result = service.continue_turn(self.session.session_id)

        prompt = backend.requests[1].messages[1].content
        self.assertIn("IMMEDIATE PREVIOUS BEAT\nTURN 1", prompt)
        self.assertIn("Mark offers the brass key, then waits for your answer.", prompt)
        self.assertIn('"holder_id":"player"', prompt)
        self.assertIn('"reason":"Mark entrusts the key to you."', prompt)
        self.assertLess(prompt.index("IMMEDIATE PREVIOUS BEAT"), prompt.index("PLAYER INPUT\nAUTOPLAY CONTINUATION"))
        self.assertEqual(result.context.diagnostics.section_chars["previous_beat"], len(
            prompt[prompt.index("IMMEDIATE PREVIOUS BEAT"):prompt.index("PLAYER INPUT\nAUTOPLAY CONTINUATION")].rstrip()
        ))
        self.assertEqual(result.context.diagnostics.turn_numbers, [1])

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

    def test_length_limited_response_uses_compact_fresh_retry_not_json_repair(self) -> None:
        backend = ScriptedModelBackend([
            ModelResponse(content='```json\n{"narration":"An unfinished response', raw_response={"choices": []}, finish_reason="length"),
            '{"narration":"Mark considers your request.","events":[]}',
        ])
        service = self._turn_service(backend)

        result = service.submit_turn(self.session.session_id, "I ask Mark for help.")

        self.assertEqual(result.turn.turn_number, 1)
        self.assertEqual(len(backend.requests), 2)
        self.assertEqual(backend.requests[1].temperature, 0.2)
        self.assertIn("TRUNCATION RETRY", backend.requests[1].messages[1].content)
        self.assertNotIn("ORIGINAL INVALID RESPONSE", backend.requests[1].messages[1].content)
        self.assertLess(
            sum(len(message.content) for message in backend.requests[1].messages),
            sum(len(message.content) for message in backend.requests[0].messages),
        )
        calls = self.connection.execute("SELECT attempt_number, validation_errors_json FROM model_calls ORDER BY attempt_number").fetchall()
        self.assertEqual([row["attempt_number"] for row in calls], [1, 2])
        self.assertIn("completion limit", calls[0]["validation_errors_json"])

    def test_continue_length_retry_retains_immediate_previous_beat(self) -> None:
        backend = ScriptedModelBackend([
            '{"narration":"Mark points to a fresh trail beyond the observatory.","events":[]}',
            ModelResponse(content='{"narration":"An unfinished response', raw_response={"choices": []}, finish_reason="length"),
            '{"narration":"Mark waits beside the trail for your response.","events":[]}',
        ])
        service = self._turn_service(backend)

        service.submit_turn(self.session.session_id, "I ask Mark where the trail leads.")
        result = service.continue_turn(self.session.session_id)

        retry_prompt = backend.requests[2].messages[1].content
        self.assertIn("TRUNCATION RETRY", retry_prompt)
        self.assertIn("IMMEDIATE PREVIOUS BEAT\nTURN 1", retry_prompt)
        self.assertIn("Mark points to a fresh trail beyond the observatory.", retry_prompt)
        self.assertIn("VALIDATED STATE EVENTS:", retry_prompt)
        self.assertEqual(result.context.diagnostics.turn_numbers, [1])

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

    def test_relaxed_item_management_discards_invalid_item_events_without_retry(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        world_path = Path(temporary.name) / "ember_hollow"
        shutil.copytree(SAMPLE_WORLD, world_path)
        config_path = world_path / "world.toml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                "relaxed_item_management = false", "relaxed_item_management = true"
            ),
            encoding="utf-8",
        )
        world = load_world(world_path)
        ids = iter(f"relaxed_id_{number}" for number in range(100))
        game = GameService(self.connection, world, clock=lambda: NOW, id_factory=lambda: next(ids))
        session, _ = game.create_session("Relaxed items")
        backend = ScriptedModelBackend([
            '{"narration":"You take the key while ignoring a false lead.","events":['
            '{"type":"transfer_item","item_id":"imaginary_key","holder_type":"actor","holder_id":"player","reason":"The model invented this item."},'
            '{"type":"transfer_item","item_id":"brass_key","holder_type":"actor","holder_id":"imaginary_holder","reason":"The model invented this holder."},'
            '{"type":"transfer_item","item_id":"brass_key","holder_type":"actor","holder_id":"player","reason":"Mark gives you the real key."}'
            ']}'
        ])
        service = TurnService(self.connection, world, backend, clock=lambda: NOW, id_factory=lambda: next(ids))

        result = service.submit_turn(session.session_id, "I ask Mark for the key.")

        self.assertEqual(len(backend.requests), 1)
        self.assertEqual(result.turn.turn_number, 1)
        self.assertEqual(game.state_for_session(session.session_id).items["brass_key"].holder_id, "player")
        rows = self.connection.execute("SELECT payload_json FROM state_events").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIn('"item_id":"brass_key"', rows[0]["payload_json"])

    def test_strict_item_management_repairs_invalid_item_event_by_default(self) -> None:
        backend = ScriptedModelBackend([
            '{"narration":"A false lead.","events":[{"type":"transfer_item","item_id":"imaginary_key","holder_type":"actor","holder_id":"player","reason":"The model invented this item."}]}',
            '{"narration":"Mark considers your request.","events":[]}',
        ])
        service = self._turn_service(backend)

        result = service.submit_turn(self.session.session_id, "I ask Mark for the key.")

        self.assertEqual(result.turn.turn_number, 1)
        self.assertEqual(len(backend.requests), 2)
        self.assertIn("transfer_item.item_id 'imaginary_key' does not exist", backend.requests[1].messages[1].content)

    def test_relaxed_quest_management_discards_invalid_quest_events_without_retry(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        world_path = Path(temporary.name) / "ember_hollow"
        shutil.copytree(SAMPLE_WORLD, world_path)
        config_path = world_path / "world.toml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                "relaxed_quest_management = false", "relaxed_quest_management = true"
            ),
            encoding="utf-8",
        )
        world = load_world(world_path)
        ids = iter(f"relaxed_quest_id_{number}" for number in range(100))
        game = GameService(self.connection, world, clock=lambda: NOW, id_factory=lambda: next(ids))
        session, _ = game.create_session("Relaxed quests")
        backend = ScriptedModelBackend([
            '{"narration":"The gate is now your goal.","events":['
            '{"type":"set_quest_status","quest_id":"imaginary_quest","status":"active","reason":"The model invented this quest."},'
            '{"type":"set_quest_status","quest_id":"west_gate","status":"resolved","reason":"The model invented this status."},'
            '{"type":"set_quest_status","quest_id":"west_gate","status":"active","reason":"You commit to opening the gate."}'
            ']}'
        ])
        service = TurnService(self.connection, world, backend, clock=lambda: NOW, id_factory=lambda: next(ids))

        result = service.submit_turn(session.session_id, "I decide to open the gate.")

        self.assertEqual(len(backend.requests), 1)
        self.assertEqual(result.turn.turn_number, 1)
        self.assertEqual(game.state_for_session(session.session_id).quests["west_gate"].status, "active")
        rows = self.connection.execute("SELECT payload_json FROM state_events").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIn('"status":"active"', rows[0]["payload_json"])

    def test_strict_quest_management_repairs_invalid_quest_event_by_default(self) -> None:
        backend = ScriptedModelBackend([
            '{"narration":"A false objective.","events":[{"type":"set_quest_status","quest_id":"imaginary_quest","status":"active","reason":"The model invented this quest."}]}',
            '{"narration":"Mark considers your request.","events":[]}',
        ])
        service = self._turn_service(backend)

        result = service.submit_turn(self.session.session_id, "I ask Mark about the gate.")

        self.assertEqual(result.turn.turn_number, 1)
        self.assertEqual(len(backend.requests), 2)
        self.assertIn("set_quest_status.quest_id 'imaginary_quest' does not exist", backend.requests[1].messages[1].content)

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
