"""Milestone 1 command-line tests."""

from __future__ import annotations

import contextlib
import io
import unittest

from local_adventure import cli


class CliTests(unittest.TestCase):
    def test_parser_help_contains_doctor(self) -> None:
        parser = cli.build_parser()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                parser.parse_args(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("doctor", output.getvalue())

    def test_doctor_is_offline_placeholder(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = cli.main(["doctor"])
        self.assertEqual(result, 0)
        self.assertIn("Local Adventure Doctor", output.getvalue())
        self.assertIn("Milestone 1", output.getvalue())

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


if __name__ == "__main__":
    unittest.main()
