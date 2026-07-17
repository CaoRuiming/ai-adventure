"""Cross-file validation for parsed authored-world content."""

from __future__ import annotations

from ..errors import WorldValidationError
from .models import LoadedWorld


def validate_world(world: LoadedWorld) -> None:
    """Validate references and scenario consistency with actionable errors."""
    root = world.root
    _require(world.config.default_scenario in world.scenarios, root, "world.toml", "default_scenario", "references a missing scenario")
    for actor in world.actors.values():
        _require(actor.location_id in world.locations, root, f"entities/actors/{actor.id}.toml", "location_id", "references a missing location")
        for target_id, dimensions in actor.relationships.items():
            _require(target_id in world.actors, root, f"entities/actors/{actor.id}.toml", "relationships", "references a missing actor")
            _require(all(isinstance(value, int) and not isinstance(value, bool) for value in dimensions.values()), root, f"entities/actors/{actor.id}.toml", "relationships", "values must be integers")
    for location in world.locations.values():
        for connection in location.connections:
            _require(connection in world.locations, root, f"entities/locations/{location.id}.toml", "connections", "references a missing location")
    for item in world.items.values():
        if item.initial_holder_type == "actor":
            _require(item.initial_holder_id in world.actors, root, f"entities/items/{item.id}.toml", "initial_holder_id", "references a missing actor")
        if item.initial_holder_type == "location":
            _require(item.initial_holder_id in world.locations, root, f"entities/items/{item.id}.toml", "initial_holder_id", "references a missing location")
    for scenario in world.scenarios.values():
        source = f"scenarios/{scenario.id}.toml"
        _require(scenario.player_actor_id in world.actors, root, source, "player_actor_id", "references a missing actor")
        _require(scenario.starting_location_id in world.locations, root, source, "starting_location_id", "references a missing location")
        _require(all(actor_id in world.actors for actor_id in scenario.active_actor_ids), root, source, "active_actor_ids", "references a missing actor")
        _require(all(quest_id in world.quests for quest_id in scenario.active_quest_ids), root, source, "active_quest_ids", "references a missing quest")
        players = [actor_id for actor_id in scenario.active_actor_ids if world.actors[actor_id].is_player]
        _require(len(players) == 1, root, source, "active_actor_ids", "must include exactly one player actor")
        _require(players[0] == scenario.player_actor_id, root, source, "player_actor_id", "must identify the active player actor")
        _require(world.actors[scenario.player_actor_id].location_id == scenario.starting_location_id, root, source, "starting_location_id", "must match the player actor location")
    entity_ids = set(world.actors) | set(world.locations) | set(world.items) | set(world.quests)
    for document in world.lore_documents:
        _require(all(entity_id in entity_ids for entity_id in document.metadata.entity_ids), root, document.relative_path, "entity_ids", "references a missing entity")
    seen_lore_ids: set[str] = set()
    for document in world.lore_documents:
        _require(document.metadata.id not in seen_lore_ids, root, document.relative_path, "id", "duplicates another lore document")
        seen_lore_ids.add(document.metadata.id)
    seen_skill_ids: set[str] = set()
    for skill in world.skills:
        _require(skill.config.id not in seen_skill_ids, root, skill.relative_path, "id", "duplicates another skill")
        seen_skill_ids.add(skill.config.id)
        _require(all(entity_id in entity_ids for entity_id in skill.config.entity_ids), root, skill.relative_path, "entity_ids", "references a missing entity")


def _require(condition: bool, root: str, relative_path: str, field: str, message: str) -> None:
    if not condition:
        raise WorldValidationError(f"{root}/{relative_path}: {field}: {message}")
