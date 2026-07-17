"""Tests for bounded, deterministic lore front-matter parsing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_adventure.content.frontmatter import MAX_LORE_BYTES, read_lore_document
from local_adventure.errors import ContentParseError


class FrontMatterTests(unittest.TestCase):
    def test_parses_valid_toml_front_matter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lore.md"
            path.write_text("+++\nid = 'lore_entry'\ntitle = 'Lore'\nkind = 'setting'\n+++\nBody\n", encoding="utf-8")
            document = read_lore_document(path, "lore.md")
        self.assertEqual(document.metadata.id, "lore_entry")
        self.assertEqual(document.body, "Body\n")

    def test_derives_metadata_without_front_matter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "old-road.md"
            path.write_text("# Old Road\n\nDusty.\n", encoding="utf-8")
            document = read_lore_document(path, "places/old-road.md")
        self.assertEqual(document.metadata.id, "places_old_road")
        self.assertEqual(document.metadata.title, "Old Road")
        self.assertEqual(document.metadata.priority, 0.5)

    def test_missing_closing_delimiter_has_path_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "broken.md"
            path.write_text("+++\nid = 'broken'\n", encoding="utf-8")
            with self.assertRaisesRegex(ContentParseError, r"broken\.md.*closing"):
                read_lore_document(path, "broken.md")

    def test_invalid_toml_and_oversized_files_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            invalid = directory / "invalid.md"
            invalid.write_text("+++\nid = [\n+++\n", encoding="utf-8")
            with self.assertRaisesRegex(ContentParseError, r"invalid\.md.*TOML"):
                read_lore_document(invalid, "invalid.md")
            large = directory / "large.md"
            large.write_bytes(b"x" * (MAX_LORE_BYTES + 1))
            with self.assertRaisesRegex(ContentParseError, r"large\.md.*1 MiB"):
                read_lore_document(large, "large.md")

