"""Deterministic model backend used by offline tests."""

from __future__ import annotations

from collections import deque

from .backend import ModelRequest, ModelResponse


class ScriptedModelBackend:
    """Return queued response text or raise queued exceptions in order."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = deque(responses)
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("scripted model backend received more requests than scripted responses")
        response = self._responses.popleft()
        if isinstance(response, Exception):
            raise response
        return ModelResponse(content=response, raw_response={"scripted": True})
