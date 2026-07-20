"""Semantic validation for state events and runtime-state invariants."""

from __future__ import annotations

from math import isfinite
import re

from ..content.models import GameplaySettings, ID_PATTERN
from ..errors import StateEventValidationError, StateInvariantError
from .events import AdjustRelationshipEvent, AdjustStatEvent, Event, MoveActorEvent, SetFlagEvent, SetQuestStatusEvent, TransferItemEvent
from .models import GameState


def validate_event(
    state: GameState,
    event: Event,
    gameplay: GameplaySettings,
    *,
    model_generated: bool = True,
) -> Event:
    """Validate an event against state and return its normalized committed form."""
    validate_state(state, gameplay)
    if isinstance(event, MoveActorEvent):
        _require(event.actor_id in state.actors, f"move_actor.actor_id '{event.actor_id}' does not exist")
        _require(event.location_id in state.locations, f"move_actor.location_id '{event.location_id}' does not exist")
        _require(not (model_generated and event.allow_unconnected), "move_actor.allow_unconnected is not permitted for model events")
        current = state.actors[event.actor_id].location_id
        _require(event.location_id == current or event.allow_unconnected or event.location_id in state.locations[current].connections,
            "move_actor.location_id is not connected to the actor's current location")
    elif isinstance(event, TransferItemEvent):
        _require(event.item_id in state.items, f"transfer_item.item_id '{event.item_id}' does not exist")
        if event.holder_type == "none":
            _require(not event.holder_id, "transfer_item.holder_id must be empty when holder_type is none")
        elif event.holder_type == "actor":
            _require(event.holder_id in state.actors, f"transfer_item.holder_id '{event.holder_id}' does not name an actor")
        else:
            _require(event.holder_id in state.locations, f"transfer_item.holder_id '{event.holder_id}' does not name a location")
    elif isinstance(event, AdjustStatEvent):
        _require(event.actor_id in state.actors, f"adjust_stat.actor_id '{event.actor_id}' does not exist")
        actor = state.actors[event.actor_id]
        _require(event.stat in actor.stats, f"adjust_stat.stat '{event.stat}' does not exist")
        current = actor.stats[event.stat]
        _require(isinstance(current, (int, float)) and not isinstance(current, bool), "adjust_stat current stat must be numeric and not boolean")
        _require(abs(event.delta) <= gameplay.stat_delta_limit, "adjust_stat.delta exceeds configured limit")
        _require(isfinite(float(current + event.delta)), "adjust_stat result must be finite")
    elif isinstance(event, AdjustRelationshipEvent):
        _require(event.source_actor_id in state.actors, f"adjust_relationship.source_actor_id '{event.source_actor_id}' does not exist")
        _require(event.target_actor_id in state.actors, f"adjust_relationship.target_actor_id '{event.target_actor_id}' does not exist")
        _require(abs(event.delta) <= gameplay.stat_delta_limit, "adjust_relationship.delta exceeds configured limit")
        current = state.actors[event.source_actor_id].relationships.get(event.target_actor_id, {}).get(event.dimension, 0)
        result = max(gameplay.relationship_minimum, min(gameplay.relationship_maximum, current + event.delta))
        return event.model_copy(update={"applied_delta": result - current})
    elif isinstance(event, SetQuestStatusEvent):
        _require(event.quest_id in state.quests, f"set_quest_status.quest_id '{event.quest_id}' does not exist")
        _require(event.status in state.quests[event.quest_id].allowed_statuses, "set_quest_status.status is not allowed for this quest")
    return event


def is_noop_event(state: GameState, event: Event) -> bool:
    """Return whether an otherwise well-formed event leaves ``state`` unchanged.

    This deliberately recognizes only effects that can be checked from the
    current authoritative state. Unknown IDs and malformed holder references
    remain validation failures so the model receives a repair request instead
    of silently hiding a potentially meaningful mistake.
    """
    if isinstance(event, MoveActorEvent):
        return event.actor_id in state.actors and state.actors[event.actor_id].location_id == event.location_id
    if isinstance(event, TransferItemEvent):
        if event.item_id not in state.items:
            return False
        item = state.items[event.item_id]
        return item.holder_type == event.holder_type and item.holder_id == event.holder_id
    if isinstance(event, SetFlagEvent):
        return event.key in state.flags and state.flags[event.key] == event.value
    if isinstance(event, AdjustStatEvent):
        return event.actor_id in state.actors and event.stat in state.actors[event.actor_id].stats and event.delta == 0
    if isinstance(event, AdjustRelationshipEvent):
        return event.source_actor_id in state.actors and event.target_actor_id in state.actors and (event.applied_delta if event.applied_delta is not None else event.delta) == 0
    if isinstance(event, SetQuestStatusEvent):
        return event.quest_id in state.quests and state.quests[event.quest_id].status == event.status
    return False


def is_ignorable_item_event(state: GameState, event: Event, gameplay: GameplaySettings, *, model_generated: bool) -> bool:
    """Return whether an invalid model item transfer may safely be discarded.

    Relaxed item management is intentionally narrow: it suppresses retries for
    malformed references in a model-generated ``transfer_item`` event, but it
    never creates an item, changes an item holder, or weakens state invariants.
    Non-model events remain strict so application code cannot accidentally
    conceal a programming error.
    """
    if not (gameplay.relaxed_item_management and model_generated and isinstance(event, TransferItemEvent)):
        return False
    if event.item_id not in state.items:
        return True
    if event.holder_type == "none":
        return bool(event.holder_id)
    if event.holder_type == "actor":
        return event.holder_id not in state.actors
    return event.holder_id not in state.locations


def validate_state(state: GameState, gameplay: GameplaySettings) -> None:
    """Raise StateInvariantError when a complete state violates an invariant."""
    _invariant(state.player_actor_id in state.actors, "player actor does not exist")
    _invariant(state.actors[state.player_actor_id].is_player, "player actor must have is_player=true")
    for key, actor in state.actors.items():
        _invariant(key == actor.id, f"actor dictionary key '{key}' does not match id '{actor.id}'")
        _invariant(actor.location_id in state.locations, f"actor '{actor.id}' references missing location '{actor.location_id}'")
        for target_id, dimensions in actor.relationships.items():
            _invariant(target_id in state.actors, f"actor '{actor.id}' relationship target '{target_id}' does not exist")
            for dimension, value in dimensions.items():
                _invariant(bool(re.fullmatch(ID_PATTERN, dimension)), f"relationship dimension '{dimension}' is invalid")
                _invariant(isinstance(value, int) and not isinstance(value, bool), "relationship value must be an integer")
                _invariant(gameplay.relationship_minimum <= value <= gameplay.relationship_maximum, "relationship value is outside configured bounds")
    for key, location in state.locations.items():
        _invariant(key == location.id, f"location dictionary key '{key}' does not match id '{location.id}'")
        _invariant(all(connection in state.locations for connection in location.connections), f"location '{location.id}' references a missing connection")
    for key, item in state.items.items():
        _invariant(key == item.id, f"item dictionary key '{key}' does not match id '{item.id}'")
        if item.holder_type == "actor":
            _invariant(item.holder_id in state.actors, f"item '{item.id}' references missing actor holder")
        elif item.holder_type == "location":
            _invariant(item.holder_id in state.locations, f"item '{item.id}' references missing location holder")
        else:
            _invariant(not item.holder_id, f"item '{item.id}' must have no holder id")
    for key, quest in state.quests.items():
        _invariant(key == quest.id, f"quest dictionary key '{key}' does not match id '{quest.id}'")
        _invariant(quest.status in quest.allowed_statuses, f"quest '{quest.id}' has a disallowed status")
    for key in state.flags:
        _invariant(bool(re.fullmatch(ID_PATTERN, key)), f"flag key '{key}' is invalid")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StateEventValidationError(message)


def _invariant(condition: bool, message: str) -> None:
    if not condition:
        raise StateInvariantError(message)
