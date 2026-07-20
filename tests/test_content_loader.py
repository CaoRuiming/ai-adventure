"""Tests for authored-world loading and cross-reference validation."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from local_adventure.content.loader import load_world
from local_adventure.errors import WorldValidationError


SAMPLE_WORLD = Path(__file__).parents[1] / "worlds" / "ember_hollow"


class ContentLoaderTests(unittest.TestCase):
    def copied_world(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        world = Path(temporary.name) / "ember_hollow"
        shutil.copytree(SAMPLE_WORLD, world)
        return temporary, world

    def test_loads_valid_sample_world(self) -> None:
        world = load_world(SAMPLE_WORLD)
        self.assertEqual(world.config.id, "ember_hollow")
        self.assertFalse(world.config.gameplay.relaxed_item_management)
        self.assertEqual(len(world.actors), 2)
        self.assertEqual(len(world.lore_documents), 3)
        self.assertEqual(len(world.skills), 1)

    def test_missing_actor_reference_includes_path_and_field(self) -> None:
        temporary, world = self.copied_world()
        self.addCleanup(temporary.cleanup)
        path = world / "entities" / "items" / "brass_key.toml"
        path.write_text(path.read_text(encoding="utf-8").replace('initial_holder_id = "mark"', 'initial_holder_id = "missing"'), encoding="utf-8")
        with self.assertRaisesRegex(WorldValidationError, r"entities/items/brass_key\.toml: initial_holder_id"):
            load_world(world)

    def test_two_player_actors_fails_with_scenario_context(self) -> None:
        temporary, world = self.copied_world()
        self.addCleanup(temporary.cleanup)
        path = world / "entities" / "actors" / "mark.toml"
        path.write_text(path.read_text(encoding="utf-8").replace("is_player = false", "is_player = true"), encoding="utf-8")
        with self.assertRaisesRegex(WorldValidationError, r"scenarios/opening\.toml: active_actor_ids"):
            load_world(world)

    def test_invalid_id_and_connection_context(self) -> None:
        temporary, world = self.copied_world()
        self.addCleanup(temporary.cleanup)
        path = world / "entities" / "locations" / "observatory.toml"
        path.write_text(path.read_text(encoding="utf-8").replace('connections = ["west_gate"]', 'connections = ["missing"]'), encoding="utf-8")
        with self.assertRaisesRegex(WorldValidationError, r"entities/locations/observatory\.toml: connections"):
            load_world(world)

    def test_rejects_lore_symlink_that_escapes_world(self) -> None:
        temporary, world = self.copied_world()
        self.addCleanup(temporary.cleanup)
        outside = Path(temporary.name) / "outside.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        escaped = world / "lore" / "escaped.md"
        escaped.symlink_to(outside)
        with self.assertRaisesRegex(WorldValidationError, r"escapes selected world root"):
            load_world(world)

    def test_rejects_required_file_symlink_that_escapes_world(self) -> None:
        temporary, world = self.copied_world()
        self.addCleanup(temporary.cleanup)
        outside = Path(temporary.name) / "outside.toml"
        outside.write_text((world / "world.toml").read_text(encoding="utf-8"), encoding="utf-8")
        config = world / "world.toml"
        config.unlink()
        config.symlink_to(outside)
        with self.assertRaisesRegex(WorldValidationError, r"world\.toml: path escapes selected world root"):
            load_world(world)
