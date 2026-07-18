"""LM Studio's OpenAI-compatible HTTP transport."""

from __future__ import annotations

import json
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..errors import ModelConnectionError, ModelProtocolError, ModelTimeoutError
from .backend import ModelRequest, ModelResponse

MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_ERROR_DETAIL_BYTES = 8 * 1024


class LMStudioBackend:
    """Call LM Studio's stateless OpenAI-compatible endpoints."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def generate(self, request: ModelRequest) -> ModelResponse:
        """POST a text-mode completion request.

        Application-side Pydantic and event validation remains authoritative.
        The prompt requires one JSON object, while text mode avoids both the
        nested-schema grammar limit and unsupported ``json_object`` mode in
        some LM Studio OpenAI-compatible servers.
        """
        payload = {
            "model": request.model,
            "messages": [message.model_dump(mode="json") for message in request.messages],
            "response_format": {"type": "text"},
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }
        raw, duration_ms = self._request_json("/v1/chat/completions", payload, request.timeout_seconds, request.api_token)
        try:
            choices = raw["choices"]
            if not isinstance(choices, list) or not choices:
                raise ValueError("choices must be a non-empty list")
            message = choices[0]["message"]
            content = message["content"]
            if not isinstance(content, str):
                raise ValueError("choices[0].message.content must be a string")
            finish_reason = _optional_str(choices[0].get("finish_reason"))
        except (KeyError, TypeError, ValueError) as error:
            raise ModelProtocolError(f"LM Studio response is incomplete: {error}") from error
        usage = raw.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return ModelResponse(
            content=content, raw_response=raw,
            prompt_eval_count=_optional_int(usage.get("prompt_tokens")),
            eval_count=_optional_int(usage.get("completion_tokens")),
            duration_ms=duration_ms,
            finish_reason=finish_reason,
        )

    def list_models(self, timeout_seconds: int = 10, api_token: str | None = None) -> list[str]:
        """Return exact model IDs currently advertised by the endpoint."""
        raw, _duration_ms = self._request_json("/v1/models", None, timeout_seconds, api_token)
        data = raw.get("data")
        if not isinstance(data, list):
            raise ModelProtocolError("LM Studio model list is missing a data list")
        identifiers: list[str] = []
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ModelProtocolError("LM Studio model list contains an invalid model entry")
            identifiers.append(item["id"])
        return identifiers

    def model_is_available(self, model: str, timeout_seconds: int = 10, api_token: str | None = None) -> bool:
        """Check whether an exact configured model ID is advertised."""
        return model in self.list_models(timeout_seconds, api_token)

    def _request_json(self, path: str, payload: dict[str, Any] | None, timeout_seconds: int, api_token: str | None) -> tuple[dict[str, Any], int]:
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        method = "GET"
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        started = time.monotonic_ns()
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                if response.status != 200:
                    raise ModelProtocolError(f"LM Studio returned HTTP {response.status}")
                body = _read_limited(response)
        except ModelProtocolError:
            raise
        except HTTPError as error:
            detail = _http_error_detail(error, api_token)
            suffix = f": {detail}" if detail else ""
            raise ModelProtocolError(f"LM Studio returned HTTP {error.code}{suffix}") from error
        except (TimeoutError, socket.timeout) as error:
            raise ModelTimeoutError("LM Studio request timed out") from error
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise ModelTimeoutError("LM Studio request timed out") from error
            raise ModelConnectionError("unable to reach LM Studio; start its local server or check base_url") from error
        except OSError as error:
            raise ModelConnectionError("unable to reach LM Studio; start its local server or check base_url") from error
        try:
            decoded = body.decode("utf-8")
            parsed = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModelProtocolError("LM Studio returned malformed JSON") from error
        if not isinstance(parsed, dict):
            raise ModelProtocolError("LM Studio response must be a JSON object")
        return parsed, (time.monotonic_ns() - started) // 1_000_000


def _read_limited(response: Any) -> bytes:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ModelProtocolError("LM Studio response exceeds the 32 MiB limit")
    return body


def _http_error_detail(error: HTTPError, api_token: str | None) -> str:
    """Return a bounded, credential-safe detail from an HTTP error body."""
    try:
        body = error.read(MAX_ERROR_DETAIL_BYTES + 1)
    except OSError:
        return ""
    finally:
        error.close()
    truncated = len(body) > MAX_ERROR_DETAIL_BYTES
    text = body[:MAX_ERROR_DETAIL_BYTES].decode("utf-8", errors="replace").strip()
    if api_token:
        text = text.replace(api_token, "[redacted]")
    if not text:
        return ""
    return text + " [error body truncated]" if truncated else text


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
