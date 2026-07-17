"""Offline lore indexing, retrieval, and context-budget tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from local_adventure.content.loader import load_world
from local_adventure.context.builder import ContextBuilder
from local_adventure.lore.indexer import reindex_world
from local_adventure.lore.query import retrieve_lore
from local_adventure.state.models import build_initial_state
from local_adventure.storage.connection import open_connection
from local_adventure.storage.migrations import apply_migrations
from local_adventure.storage.repositories import WorldRepository

ROOT = Path(__file__).resolve().parents[1]


class LoreAndContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.connection = open_connection(Path(self.temporary.name) / "test.sqlite3")
        apply_migrations(self.connection)
        self.world = load_world(ROOT / "worlds" / "ember_hollow")
        with self.connection:
            WorldRepository(self.connection).upsert(self.world.config.id, self.world.root, "test", self.world.config.title)
        self.state = build_initial_state(self.world)

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary.cleanup()

    def test_indexing_is_incremental_and_retrieval_is_deterministic(self) -> None:
        first = reindex_world(self.connection, self.world)
        second = reindex_world(self.connection, self.world)
        self.assertEqual(first.indexed, 3)
        self.assertEqual(second.unchanged, 3)
        first_results = retrieve_lore(self.connection, self.state, "I study the old observatory", 8)
        second_results = retrieve_lore(self.connection, self.state, "I study the old observatory", 8)
        self.assertEqual([item.document.document_id for item in first_results], [item.document.document_id for item in second_results])
        self.assertEqual(first_results[0].document.document_id, "observatory_lore")

    def test_fallback_search_works_without_fts_table(self) -> None:
        reindex_world(self.connection, self.world)
        self.connection.execute("DROP TABLE IF EXISTS lore_documents_fts")
        results = retrieve_lore(self.connection, self.state, "Tell me about the star tower", 8)
        self.assertTrue(results)
        self.assertEqual(results[0].document.document_id, "observatory_lore")

    def test_context_is_two_messages_and_within_budget(self) -> None:
        reindex_world(self.connection, self.world)
        assembled = ContextBuilder(self.connection, self.world).build(self.state, "I cautiously interrogate Mark about the observatory.")
        self.assertEqual([message.role for message in assembled.messages], ["system", "user"])
        self.assertLessEqual(assembled.diagnostics.total_chars, self.world.config.context.max_chars)
        self.assertIn('Reply with exactly one JSON object', assembled.messages[0].content)
        self.assertIn("cautious_npc", assembled.diagnostics.skill_ids)
        self.assertTrue(assembled.diagnostics.lore)

    def test_context_rejects_oversized_player_input(self) -> None:
        reindex_world(self.connection, self.world)
        with self.assertRaises(ValueError):
            ContextBuilder(self.connection, self.world).build(self.state, "x" * 16_001)


if __name__ == "__main__":
    unittest.main()
