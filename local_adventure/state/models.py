"""Pydantic models for authoritative, serializable runtime state."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..content.models import ID_PATTERN

JsonScalar = str | int | float | bool | None


class StateModel(BaseModel):
    """Base runtime model that rejects malformed persisted state."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ActorState(StateModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    location_id: str = Field(pattern=ID_PATTERN)
    is_player: bool
    description: str = ""
    stats: dict[str, JsonScalar] = Field(default_factory=dict)
    relationships: dict[str, dict[str, int]] = Field(default_factory=dict)


class LocationState(StateModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    description: str = ""
    attributes: dict[str, JsonScalar] = Field(default_factory=dict)
    connections: list[str] = Field(default_factory=list)


class ItemState(StateModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    description: str = ""
    holder_type: Literal["actor", "location", "none"]
    holder_id: str = ""
    attributes: dict[str, JsonScalar] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_holder(self) -> "ItemState":
        if self.holder_type == "none" and self.holder_id:
            raise ValueError("holder_id must be empty when holder_type is none")
        if self.holder_type != "none" and not self.holder_id:
            raise ValueError("holder_id is required unless holder_type is none")
        return self


class QuestState(StateModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    description: str = ""
    status: str = Field(min_length=1)
    allowed_statuses: list[str] = Field(min_length=1)


class GameState(StateModel):
    """The complete authoritative state for one session position."""

    schema_version: Literal[1] = 1
    world_id: str = Field(pattern=ID_PATTERN)
    scenario_id: str = Field(pattern=ID_PATTERN)
    player_actor_id: str = Field(pattern=ID_PATTERN)
    actors: dict[str, ActorState]
    locations: dict[str, LocationState]
    items: dict[str, ItemState]
    quests: dict[str, QuestState]
    flags: dict[str, JsonScalar] = Field(default_factory=dict)

    def canonical_json(self) -> str:
        """Return stable JSON suitable for state comparisons and later storage."""
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_initial_state(world: "LoadedWorld", scenario_id: str | None = None) -> GameState:
    """Construct the initial runtime state from validated authored content."""
    from ..content.models import LoadedWorld

    selected_id = scenario_id or world.config.default_scenario
    if selected_id not in world.scenarios:
        raise ValueError(f"scenario '{selected_id}' does not exist in world '{world.config.id}'")
    scenario = world.scenarios[selected_id]
    state = GameState(
        world_id=world.config.id,
        scenario_id=scenario.id,
        player_actor_id=scenario.player_actor_id,
        actors={
            actor_id: ActorState(
                id=actor.id, name=actor.name, location_id=actor.location_id,
                is_player=actor.is_player, description=actor.description,
                stats=actor.stats, relationships=actor.relationships,
            )
            for actor_id, actor in world.actors.items()
        },
        locations={
            location_id: LocationState(
                id=location.id, name=location.name, description=location.description,
                attributes=location.attributes, connections=location.connections,
            )
            for location_id, location in world.locations.items()
        },
        items={
            item_id: ItemState(
                id=item.id, name=item.name, description=item.description,
                holder_type=item.initial_holder_type, holder_id=item.initial_holder_id,
                attributes=item.attributes,
            )
            for item_id, item in world.items.items()
        },
        quests={
            quest_id: QuestState(
                id=quest.id, name=quest.name, description=quest.description,
                status=quest.initial_status, allowed_statuses=quest.allowed_statuses,
            )
            for quest_id, quest in world.quests.items()
        },
        flags=scenario.initial_flags,
    )
    from .validator import validate_state
    validate_state(state, world.config.gameplay)
    return state


def state_projection(state: GameState) -> dict[str, object]:
    """Return a stable, human-readable projection of the current state."""
    player = state.actors[state.player_actor_id]
    location = state.locations[player.location_id]
    actors_here = sorted(actor.id for actor in state.actors.values() if actor.location_id == player.location_id)
    visible_items = sorted(
        item.id for item in state.items.values()
        if (item.holder_type == "actor" and item.holder_id in actors_here)
        or (item.holder_type == "location" and item.holder_id == player.location_id)
    )
    active_quests = sorted(quest.id for quest in state.quests.values() if quest.status == "active")
    relationships = {
        actor.id: actor.relationships for actor in sorted(state.actors.values(), key=lambda value: value.id)
        if actor.id in actors_here or any(target in actors_here for target in actor.relationships)
    }
    return {
        "player": player.model_dump(mode="json"),
        "location": {"id": location.id, "name": location.name, "connections": sorted(location.connections)},
        "actors_here": actors_here,
        "visible_items": visible_items,
        "active_quests": active_quests,
        "flags": state.flags,
        "relationships": relationships,
        "valid_ids": {
            "actors": sorted(state.actors), "locations": sorted(state.locations),
            "items": sorted(state.items), "quests": sorted(state.quests),
        },
    }
