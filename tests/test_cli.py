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
    def test_parser_help_contains_doctor(self) -> None:
        parser = cli.build_parser()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                parser.parse_args(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("doctor", output.getvalue())

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


if __name__ == "__main__":
    unittest.main()
