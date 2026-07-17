"""Pure, deterministic transformations of validated state events."""

from __future__ import annotations

from ..content.models import GameplaySettings
from ..errors import StateInvariantError
from .events import AdjustRelationshipEvent, AdjustStatEvent, Event, MoveActorEvent, SetFlagEvent, SetQuestStatusEvent, TransferItemEvent
from .models import GameState
from .validator import validate_state


def apply_event(state: GameState, event: Event, gameplay: GameplaySettings) -> GameState:
    """Apply one semantically validated event without mutating ``state``."""
    data = state.model_dump(mode="python")
    if isinstance(event, MoveActorEvent):
        data["actors"][event.actor_id]["location_id"] = event.location_id
    elif isinstance(event, TransferItemEvent):
        data["items"][event.item_id]["holder_type"] = event.holder_type
        data["items"][event.item_id]["holder_id"] = event.holder_id
    elif isinstance(event, SetFlagEvent):
        data["flags"][event.key] = event.value
    elif isinstance(event, AdjustStatEvent):
        data["actors"][event.actor_id]["stats"][event.stat] += event.delta
    elif isinstance(event, AdjustRelationshipEvent):
        actor = data["actors"][event.source_actor_id]
        dimensions = actor["relationships"].setdefault(event.target_actor_id, {})
        current = dimensions.get(event.dimension, 0)
        applied = event.applied_delta if event.applied_delta is not None else event.delta
        dimensions[event.dimension] = current + applied
    elif isinstance(event, SetQuestStatusEvent):
        data["quests"][event.quest_id]["status"] = event.status
    else:  # pragma: no cover - discriminated union makes this defensive only.
        raise StateInvariantError(f"unsupported event type '{event.type}'")
    result = GameState.model_validate(data)
    validate_state(result, gameplay)
    return result


def apply_events(state: GameState, events: list[Event], gameplay: GameplaySettings) -> GameState:
    """Apply events in order, returning a new state for every invocation."""
    result = state
    for event in events:
        result = apply_event(result, event, gameplay)
    return result
