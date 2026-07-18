"""Provider-neutral, synchronous local model backend interface."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .schemas import ChatMessage


class BackendModel(BaseModel):
    """Base model for transport values with no implicit extra fields."""

    model_config = ConfigDict(extra="forbid")


class ModelRequest(BackendModel):
    """A fully assembled request ready for one text-mode model generation."""

    model: str = Field(min_length=1)
    messages: list[ChatMessage]
    temperature: float = Field(ge=0.0, le=2.0)
    max_output_tokens: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    api_token: str | None = None

    def audit_payload(self) -> dict[str, object]:
        """Return a serializable request representation without credentials."""
        payload = self.model_dump(mode="json", exclude={"api_token"})
        return payload


class ModelResponse(BackendModel):
    """The validated transport response, before proposal parsing."""

    content: str
    raw_response: dict[str, object]
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    duration_ms: int | None = None
    finish_reason: str | None = None


class ModelBackend(Protocol):
    """A backend capable of generating one structured response."""

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate one response for ``request``."""
