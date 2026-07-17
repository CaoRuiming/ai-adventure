"""Typed event proposals and committed state events."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from ..content.models import ID_PATTERN
from .models import JsonScalar


class StateEvent(BaseModel):
    """Common audit metadata for all state events."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    type: str
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must contain non-whitespace text")
        return value


class MoveActorEvent(StateEvent):
    type: Literal["move_actor"]
    actor_id: str = Field(pattern=ID_PATTERN)
    location_id: str = Field(pattern=ID_PATTERN)
    allow_unconnected: bool = False


class TransferItemEvent(StateEvent):
    type: Literal["transfer_item"]
    item_id: str = Field(pattern=ID_PATTERN)
    holder_type: Literal["actor", "location", "none"]
    holder_id: str = ""


class SetFlagEvent(StateEvent):
    type: Literal["set_flag"]
    key: str = Field(pattern=ID_PATTERN)
    value: JsonScalar


class AdjustStatEvent(StateEvent):
    type: Literal["adjust_stat"]
    actor_id: str = Field(pattern=ID_PATTERN)
    stat: str = Field(pattern=ID_PATTERN)
    delta: float | int


class AdjustRelationshipEvent(StateEvent):
    type: Literal["adjust_relationship"]
    source_actor_id: str = Field(pattern=ID_PATTERN)
    target_actor_id: str = Field(pattern=ID_PATTERN)
    dimension: str = Field(pattern=ID_PATTERN)
    delta: int
    applied_delta: int | None = None


class SetQuestStatusEvent(StateEvent):
    type: Literal["set_quest_status"]
    quest_id: str = Field(pattern=ID_PATTERN)
    status: str = Field(min_length=1)


Event = Annotated[
    MoveActorEvent | TransferItemEvent | SetFlagEvent | AdjustStatEvent | AdjustRelationshipEvent | SetQuestStatusEvent,
    Field(discriminator="type"),
]
EVENT_ADAPTER = TypeAdapter(Event)


def parse_event(value: object) -> Event:
    """Parse a raw event using the discriminated event union."""
    return EVENT_ADAPTER.validate_python(value)
