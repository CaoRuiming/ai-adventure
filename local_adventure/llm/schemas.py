"""Schemas exchanged with model backends."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..errors import ProposalValidationError
from ..state.events import Event


class SchemaModel(BaseModel):
    """Reject fields outside the documented model protocol."""

    model_config = ConfigDict(extra="forbid")


class ChatMessage(SchemaModel):
    """One self-contained OpenAI-compatible chat message."""

    role: str = Field(pattern="^(system|user|assistant)$")
    content: str


class TurnProposal(SchemaModel):
    """Narration plus non-authoritative proposed state events."""

    narration: str = Field(max_length=16_000)
    events: list[Event] = Field(default_factory=list)

    @field_validator("narration")
    @classmethod
    def narration_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must contain non-whitespace text")
        return value


def parse_turn_proposal(content: str) -> TurnProposal:
    """Parse one unwrapped JSON proposal returned by a model."""
    if content.strip().startswith("```"):
        raise ProposalValidationError("model response must be JSON without a Markdown code fence")
    try:
        value = json.loads(content)
    except json.JSONDecodeError as error:
        raise ProposalValidationError(f"model response is not valid JSON: {error.msg}") from error
    try:
        return TurnProposal.model_validate(value)
    except ValidationError as error:
        raise ProposalValidationError(f"model response does not match turn proposal schema: {error}") from error
