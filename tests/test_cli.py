"""Milestone 1 command-line tests."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_adventure import cli
from local_adventure.llm.backend import ModelResponse
from local_adventure.storage.connection import open_connection
from local_adventure.storage.migrations import apply_migrations
from local_adventure.storage.repositories import SessionRepository


class CliTests(unittest.TestCase):
    @patch("local_adventure.cli.importlib.import_module")
    def test_line_editing_loads_readline_when_available(self, import_module: object) -> None:
        cli._enable_line_editing()
        import_module.assert_called_once_with("readline")

    @patch("local_adventure.cli.importlib.import_module", side_effect=ImportError)
    def test_line_editing_is_optional_when_readline_is_unavailable(self, _import_module: object) -> None:
        cli._enable_line_editing()

    def test_prompt_notification_uses_terminal_bell_only_for_interactive_output(self) -> None:
        interactive_output = unittest.mock.Mock()
        interactive_output.isatty.return_value = True
        cli._notify_prompt_ready(interactive_output)
        interactive_output.write.assert_called_once_with("\a")
        interactive_output.flush.assert_called_once_with()

        redirected_output = io.StringIO()
        cli._notify_prompt_ready(redirected_output)
        self.assertEqual(redirected_output.getvalue(), "")

    @patch("local_adventure.cli._notify_prompt_ready")
    def test_play_notifies_immediately_before_each_action_prompt(self, notify: object) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            replies = iter(["/quit"])

            def read_input(_prompt: str) -> str:
                self.assertTrue(notify.called)
                return next(replies)

            self.assertEqual(cli.play_game(world_path=Path("worlds/ember_hollow"), input_fn=read_input, output=io.StringIO()), 0)
            notify.assert_called_once()

    def test_parser_help_contains_doctor(self) -> None:
        parser = cli.build_parser()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                parser.parse_args(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("doctor", output.getvalue())

    def test_play_parser_accepts_actions_file_for_new_and_existing_sessions(self) -> None:
        parser = cli.build_parser()
        for selector in (["--world", "worlds/ember_hollow"], ["--session", "saved-id"]):
            args = parser.parse_args(["play", *selector, "--actions-file", "actions.txt"])
            self.assertEqual(args.actions_file, Path("actions.txt"))

    @patch("local_adventure.cli.LMStudioBackend.model_is_available", return_value=False)
    def test_doctor_reports_local_checks_when_model_is_unavailable(self, _model_available: object) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = cli.main(["doctor"])
        self.assertEqual(result, 0)
        self.assertIn("Local Adventure Doctor", output.getvalue())
        self.assertIn("SQLite", output.getvalue())
        self.assertIn("model play unavailable", output.getvalue())

    def test_no_command_prints_help_without_creating_runtime_files(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = cli.main([])
        self.assertEqual(result, 0)
        self.assertIn("usage:", output.getvalue())

    def test_validate_world_prints_authored_content_counts(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = cli.main(["validate-world", "--world", "worlds/ember_hollow"])
        self.assertEqual(result, 0)
        self.assertIn("World valid: Ember Hollow", output.getvalue())
        self.assertIn("actors=2", output.getvalue())

    def test_sessions_create_and_list_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli.main(["sessions", "create", "--world", "worlds/ember_hollow", "--name", "CLI Test"]), 0)
                self.assertEqual(cli.main(["sessions", "list"]), 0)
            self.assertIn("CLI Test", output.getvalue())

    def test_export_command_writes_json_for_a_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            output_path = Path(temporary) / "session.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli.main(["sessions", "create", "--world", "worlds/ember_hollow", "--name", "Export Test"]), 0)
            connection = open_connection(Path(temporary) / "local-adventure.sqlite3")
            try:
                apply_migrations(connection)
                session_id = SessionRepository(connection).list_all()[0].session_id
            finally:
                connection.close()
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli.main(["export", "--session", session_id, "--format", "json", "--output", str(output_path)]), 0)
            self.assertTrue(output_path.exists())
            self.assertIn('"export_schema_version": 1', output_path.read_text(encoding="utf-8"))

    @patch("local_adventure.cli.LMStudioBackend.generate")
    def test_play_dispatches_commands_and_autosaves_a_valid_turn(self, generate: object) -> None:
        generate.return_value = ModelResponse(
            content='{"narration":"Mark nods.","events":[]}', raw_response={"choices": []}
        )
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            replies = iter(["/where", "/inventory", "I greet Mark.", "/history 1", "/quit"])
            output = io.StringIO()
            self.assertEqual(cli.play_game(world_path=Path("worlds/ember_hollow"), input_fn=lambda _prompt: next(replies), output=output), 0)
            text = output.getvalue()
            self.assertIn("Mark nods.", text)
            self.assertIn("TURN 1", text)
            connection = open_connection(Path(temporary) / "local-adventure.sqlite3")
            try:
                apply_migrations(connection)
                self.assertEqual(len(SessionRepository(connection).list_all()), 1)
                self.assertIsNotNone(SessionRepository(connection).list_all()[0].head_turn_id)
            finally:
                connection.close()

    @patch("local_adventure.cli.LMStudioBackend.generate")
    def test_play_continue_generates_and_autosaves_one_model_directed_turn(self, generate: object) -> None:
        generate.return_value = ModelResponse(
            content='{"narration":"Mark listens to the wind.","events":[]}', raw_response={"choices": []}
        )
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            output = io.StringIO()
            replies = iter(["/continue", "/history 1", "/quit"])

            self.assertEqual(cli.play_game(world_path=Path("worlds/ember_hollow"), input_fn=lambda _prompt: next(replies), output=output), 0)

            self.assertIn("Mark listens to the wind.", output.getvalue())
            self.assertIn("PLAYER:\n/continue", output.getvalue())
            self.assertIn("/continue", cli._HELP)
            connection = open_connection(Path(temporary) / "local-adventure.sqlite3")
            try:
                apply_migrations(connection)
                session = SessionRepository(connection).list_all()[0]
                turn = connection.execute("SELECT turn_number, player_input FROM turns WHERE session_id = ?", (session.session_id,)).fetchone()
                self.assertEqual((turn["turn_number"], turn["player_input"]), (1, "/continue"))
            finally:
                connection.close()

    @patch("local_adventure.cli.LMStudioBackend.generate")
    def test_play_separates_user_prompt_from_surrounding_output(self, generate: object) -> None:
        generate.return_value = ModelResponse(
            content='{"narration":"Mark nods.","events":[]}', raw_response={"choices": []}
        )
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            replies = iter(["I greet Mark.", "/quit"])
            output = io.StringIO()

            def read_input(prompt: str) -> str:
                output.write(prompt)
                return next(replies)

            self.assertEqual(cli.play_game(world_path=Path("worlds/ember_hollow"), input_fn=read_input, output=output), 0)
            self.assertIn("\n> \n", output.getvalue())

    @patch("local_adventure.cli.LMStudioBackend.generate", side_effect=KeyboardInterrupt)
    def test_play_cancellation_does_not_commit_a_turn(self, _generate: object) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            replies = iter(["I wait.", "/quit"])
            output = io.StringIO()
            self.assertEqual(cli.play_game(world_path=Path("worlds/ember_hollow"), input_fn=lambda _prompt: next(replies), output=output), 0)
            self.assertIn("Model request cancelled; no turn was saved.", output.getvalue())
            connection = open_connection(Path(temporary) / "local-adventure.sqlite3")
            try:
                apply_migrations(connection)
                self.assertIsNone(SessionRepository(connection).list_all()[0].head_turn_id)
            finally:
                connection.close()

    def test_play_eof_exits_cleanly_before_a_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            output = io.StringIO()
            def end_input(_prompt: str) -> str:
                raise EOFError
            self.assertEqual(cli.play_game(world_path=Path("worlds/ember_hollow"), input_fn=end_input, output=output), 0)
            self.assertIn("Type /help for commands.", output.getvalue())

    @patch("local_adventure.cli.LMStudioBackend.generate")
    def test_actions_file_plays_live_then_returns_to_interactive_input(self, generate: object) -> None:
        generate.side_effect = [
            ModelResponse(content=f'{{"narration":"Beat {number}.","events":[]}}', raw_response={"choices": []})
            for number in range(1, 4)
        ]
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            actions = Path(temporary) / "actions.txt"
            actions.write_text("I greet Mark.\nI ask about the gate.\n", encoding="utf-8")
            output = io.StringIO()
            interactive = iter(["I wait.", "/quit"])
            prompts: list[str] = []

            def read_input(prompt: str) -> str:
                prompts.append(prompt)
                self.assertIn("Beat 2.", output.getvalue())
                return next(interactive)

            self.assertEqual(cli.play_game(world_path=Path("worlds/ember_hollow"), actions_file=actions,
                                           input_fn=read_input, output=output), 0)
            self.assertEqual(prompts, ["> ", "> "])
            text = output.getvalue()
            self.assertLess(text.index("> I greet Mark."), text.index("Beat 1."))
            self.assertLess(text.index("> I ask about the gate."), text.index("Beat 2."))
            self.assertIn("Recorded actions complete", text)
            connection = open_connection(Path(temporary) / "local-adventure.sqlite3")
            try:
                inputs = [row[0] for row in connection.execute("SELECT player_input FROM turns ORDER BY turn_number")]
                self.assertEqual(inputs, ["I greet Mark.", "I ask about the gate.", "I wait."])
            finally:
                connection.close()

    @patch("local_adventure.cli.LMStudioBackend.generate")
    def test_invalid_action_retries_twice_after_each_repair_path(self, generate: object) -> None:
        generate.side_effect = [
            ModelResponse(content="not json", raw_response={"choices": []}) for _ in range(4)
        ] + [ModelResponse(content='{"narration":"Success.","events":[]}', raw_response={"choices": []})]
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            output = io.StringIO()
            replies = iter(["I wait.", "/quit"])
            self.assertEqual(cli.play_game(world_path=Path("worlds/ember_hollow"),
                                           input_fn=lambda _prompt: next(replies), output=output), 0)
            self.assertEqual(generate.call_count, 5)
            self.assertIn("retrying action (1/2)", output.getvalue())
            self.assertIn("retrying action (2/2)", output.getvalue())
            self.assertIn("Success.", output.getvalue())
            connection = open_connection(Path(temporary) / "local-adventure.sqlite3")
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0], 1)
            finally:
                connection.close()

    @patch("local_adventure.cli.LMStudioBackend.generate")
    def test_autoplay_stops_after_retry_exhaustion_without_skipping_actions(self, generate: object) -> None:
        generate.return_value = ModelResponse(content="not json", raw_response={"choices": []})
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            actions = Path(temporary) / "actions.txt"
            actions.write_text("I wait.\nI walk away.\n", encoding="utf-8")
            output = io.StringIO()
            self.assertEqual(cli.play_game(world_path=Path("worlds/ember_hollow"), actions_file=actions,
                                           input_fn=lambda _prompt: "/quit", output=output), 0)
            self.assertEqual(generate.call_count, 6)
            self.assertNotIn("> I walk away.", output.getvalue())
            self.assertIn("Autoplay stopped", output.getvalue())
            connection = open_connection(Path(temporary) / "local-adventure.sqlite3")
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0], 0)
            finally:
                connection.close()

    @patch("local_adventure.cli.LMStudioBackend.generate", side_effect=KeyboardInterrupt)
    def test_interrupt_during_autoplay_returns_to_manual_input(self, generate: object) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            actions = Path(temporary) / "actions.txt"
            actions.write_text("I wait.\nI walk away.\n", encoding="utf-8")
            output = io.StringIO()
            self.assertEqual(cli.play_game(world_path=Path("worlds/ember_hollow"), actions_file=actions,
                                           input_fn=lambda _prompt: "/quit", output=output), 0)
            self.assertEqual(generate.call_count, 1)
            self.assertNotIn("> I walk away.", output.getvalue())
            self.assertIn("Autoplay interrupted", output.getvalue())

    def test_invalid_actions_file_does_not_create_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCAL_ADVENTURE_HOME": temporary}):
            actions = Path(temporary) / "actions.txt"
            actions.write_text("I wait.\n\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                cli.play_game(world_path=Path("worlds/ember_hollow"), actions_file=actions, output=io.StringIO())
            self.assertFalse((Path(temporary) / "local-adventure.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
