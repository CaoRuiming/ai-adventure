"""Offline tests for the LM Studio adapter and structured proposal schema."""

from __future__ import annotations

import json
import socket
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from pydantic import ValidationError

from local_adventure.errors import ModelConnectionError, ModelProtocolError, ModelTimeoutError, ProposalValidationError
from local_adventure.llm.backend import ModelRequest
from local_adventure.llm.lm_studio import LMStudioBackend, MAX_RESPONSE_BYTES
from local_adventure.llm.schemas import ChatMessage, TurnProposal, parse_turn_proposal
from local_adventure.llm.scripted import ScriptedModelBackend


class _Response:
    status = 200

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self, _limit: int) -> bytes:
        return self.payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class LMStudioBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = LMStudioBackend("http://127.0.0.1:1234/")
        self.request = ModelRequest(
            model="local-model",
            messages=[ChatMessage(role="system", content="Rules"), ChatMessage(role="user", content="Act")],
            temperature=0.8,
            max_output_tokens=1400, timeout_seconds=30, api_token="secret-token",
        )

    @patch("local_adventure.llm.lm_studio.urlopen")
    def test_completion_uses_text_mode_and_parses_content(self, mocked_open: object) -> None:
        mocked_open.return_value = _Response(json.dumps({"choices": [{"message": {"content": '{"narration": "Hello."}'}}], "usage": {"prompt_tokens": 8, "completion_tokens": 3}}).encode())
        response = self.backend.generate(self.request)
        sent = mocked_open.call_args.args[0]
        self.assertEqual(sent.full_url, "http://127.0.0.1:1234/v1/chat/completions")
        body = json.loads(sent.data)
        self.assertFalse(body["stream"])
        self.assertEqual(body["response_format"], {"type": "text"})
        self.assertEqual(sent.get_header("Authorization"), "Bearer secret-token")
        self.assertEqual(response.content, '{"narration": "Hello."}')
        self.assertEqual(response.prompt_eval_count, 8)
        self.assertEqual(response.eval_count, 3)
        self.assertNotIn("secret-token", json.dumps(self.request.audit_payload()))

    @patch("local_adventure.llm.lm_studio.urlopen")
    def test_model_discovery_uses_models_endpoint(self, mocked_open: object) -> None:
        mocked_open.return_value = _Response(b'{"data":[{"id":"other"},{"id":"local-model"}]}')
        self.assertTrue(self.backend.model_is_available("local-model"))
        sent = mocked_open.call_args.args[0]
        self.assertEqual(sent.full_url, "http://127.0.0.1:1234/v1/models")
        self.assertEqual(sent.get_method(), "GET")

    @patch("local_adventure.llm.lm_studio.urlopen")
    def test_protocol_errors_are_typed(self, mocked_open: object) -> None:
        mocked_open.return_value = _Response(b'{"choices":[]}')
        with self.assertRaises(ModelProtocolError):
            self.backend.generate(self.request)
        mocked_open.return_value = _Response(b"not json")
        with self.assertRaises(ModelProtocolError):
            self.backend.generate(self.request)
        mocked_open.return_value = _Response(b'{"choices":[{"message":{}}]}')
        with self.assertRaises(ModelProtocolError):
            self.backend.generate(self.request)

    @patch("local_adventure.llm.lm_studio.urlopen")
    def test_transport_errors_are_typed(self, mocked_open: object) -> None:
        mocked_open.side_effect = URLError(socket.timeout())
        with self.assertRaises(ModelTimeoutError):
            self.backend.generate(self.request)
        mocked_open.side_effect = URLError("connection refused")
        with self.assertRaises(ModelConnectionError):
            self.backend.generate(self.request)
        mocked_open.side_effect = HTTPError("url", 500, "error", {}, None)
        with self.assertRaises(ModelProtocolError):
            self.backend.generate(self.request)

    @patch("local_adventure.llm.lm_studio.urlopen")
    def test_http_error_includes_bounded_redacted_response_detail(self, mocked_open: object) -> None:
        mocked_open.side_effect = HTTPError(
            "url", 400, "error", {},
            BytesIO(b'{"error":"unsupported field","echo":"secret-token"}'),
        )
        with self.assertRaisesRegex(ModelProtocolError, "HTTP 400:.*unsupported field") as caught:
            self.backend.generate(self.request)
        self.assertNotIn("secret-token", str(caught.exception))
        self.assertIn("[redacted]", str(caught.exception))

    @patch("local_adventure.llm.lm_studio.urlopen")
    def test_oversized_response_is_rejected(self, mocked_open: object) -> None:
        mocked_open.return_value = _Response(b"x" * (MAX_RESPONSE_BYTES + 1))
        with self.assertRaises(ModelProtocolError):
            self.backend.generate(self.request)

    def test_turn_proposal_rejects_unknown_fields_and_code_fences(self) -> None:
        with self.assertRaises(ValidationError):
            TurnProposal.model_validate({"narration": "Hi", "analysis": "private"})
        with self.assertRaises(ProposalValidationError):
            parse_turn_proposal("```json\n{}\n```")

    def test_scripted_backend_records_requests_and_raises_scripted_error(self) -> None:
        backend = ScriptedModelBackend(["{\"narration\":\"Hi\"}", RuntimeError("offline")])
        self.assertEqual(backend.generate(self.request).content, '{"narration":"Hi"}')
        with self.assertRaisesRegex(RuntimeError, "offline"):
            backend.generate(self.request)
        self.assertEqual(backend.requests, [self.request, self.request])


if __name__ == "__main__":
    unittest.main()
