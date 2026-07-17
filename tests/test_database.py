"""Offline coverage for database setup, migrations, and atomic commits."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_adventure.app.game_service import GameService
from local_adventure.content.loader import load_world
from local_adventure.errors import ConcurrentSessionUpdateError, MigrationError
from local_adventure.state.events import SetFlagEvent
from local_adventure.storage.connection import open_connection
from local_adventure.storage.migrations import apply_migrations

SAMPLE_WORLD = Path(__file__).parents[1] / "worlds" / "ember_hollow"


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.connection = open_connection(Path(self.temporary.name) / "game.sqlite3")
        apply_migrations(self.connection, clock=lambda: "2026-07-16T00:00:00.000000Z")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary.cleanup()

    def test_migrations_are_idempotent_and_connection_is_configured(self) -> None:
        self.assertEqual(apply_migrations(self.connection), 2)
        self.assertEqual(self.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertIsNotNone(self.connection.execute("SELECT name FROM sqlite_master WHERE name = 'lore_documents'").fetchone())

    def test_missing_applied_migration_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            schema = Path(temp)
            (schema / "0001_example.sql").write_text("CREATE TABLE example (id INTEGER);", encoding="utf-8")
            connection = open_connection(schema / "test.sqlite3")
            try:
                apply_migrations(connection, schema)
                (schema / "0001_example.sql").unlink()
                with self.assertRaisesRegex(MigrationError, "previously applied migration"):
                    apply_migrations(connection, schema)
            finally:
                connection.close()

    def test_session_creation_and_atomic_turn_commit(self) -> None:
        service = _service(self.connection)
        session, _ = service.create_session("Database Test")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM lore_documents").fetchone()[0], 3)
        event = SetFlagEvent(type="set_flag", key="asked_mark", value=True, reason="The player asks.")
        turn = service.commit_turn(session.session_id, "I ask Mark.", "Mark listens.", [event])
        self.assertEqual(turn.turn_number, 1)
        self.assertTrue(service.state_for_session(session.session_id).flags["asked_mark"])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM state_events").fetchone()[0], 1)

    def test_stale_expected_head_does_not_create_a_turn(self) -> None:
        service = _service(self.connection)
        session, _ = service.create_session("Concurrency Test")
        event = SetFlagEvent(type="set_flag", key="one", value=True, reason="First.")
        service.commit_turn(session.session_id, "one", "one", [event])
        state = service.state_for_session(session.session_id)
        with self.assertRaises(ConcurrentSessionUpdateError):
            service.turns.commit(session.session_id, None, "stale", "two", "two", [], state)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0], 1)


def _service(connection):
    identifiers = iter(f"id_{number}" for number in range(100))
    return GameService(connection, load_world(SAMPLE_WORLD), clock=lambda: "2026-07-16T00:00:00.000000Z", id_factory=lambda: next(identifiers))
