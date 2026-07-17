"""Validated model-turn orchestration for authoritative game sessions."""

from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from ..content.models import LoadedWorld
from ..context.builder import TURN_OUTPUT_CONTRACT, ContextAssembly, ContextBuilder
from ..context.formatter import format_state
from ..errors import ProposalValidationError, StateEventValidationError, StateInvariantError
from ..llm.backend import ModelBackend, ModelRequest, ModelResponse
from ..llm.schemas import ChatMessage, TurnProposal, parse_turn_proposal
from ..lore.indexer import reindex_world
from ..state.events import Event
from ..state.models import GameState
from ..state.reducer import apply_event
from ..state.validator import is_noop_event, validate_event
from ..storage.repositories import ModelCallRepository, SessionRepository, SummaryRepository, TurnRecord, TurnRepository
from ..util.clocks import Clock, utc_now
from ..util.hashing import sha256_text
from ..util.json_tools import canonical_json
from .game_service import GameService

IdFactory = Callable[[], str]


@dataclass(frozen=True)
class LastTurnError:
    """Detailed non-secret diagnostic retained for the current process."""

    message: str
    validation_errors: list[str]


@dataclass(frozen=True)
class TurnResult:
    """A committed turn and its authoritative state, safe to display."""

    turn: TurnRecord
    state: GameState
    narration: str
    context: ContextAssembly


class TurnService:
    """Coordinate context, model proposals, validation, repair, and commit."""

    def __init__(self, connection: sqlite3.Connection, world: LoadedWorld, backend: ModelBackend, *, clock: Clock = utc_now, id_factory: IdFactory | None = None) -> None:
        self.connection, self.world, self.backend, self.clock = connection, world, backend, clock
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))
        self.sessions = SessionRepository(connection, clock)
        self.turns = TurnRepository(connection, clock)
        self.model_calls = ModelCallRepository(connection, clock)
        self.summaries = SummaryRepository(connection, clock)
        self.game = GameService(connection, world, clock=clock, id_factory=self._id_factory)
        self.last_error: LastTurnError | None = None

    def submit_turn(self, session_id: str, player_input: str) -> TurnResult:
        """Commit one valid model proposal, attempting one repair when allowed."""
        action = player_input.rstrip("\n")
        if not action.strip():
            raise ValueError("player input must not be empty")
        if len(action) > 16_000:
            raise ValueError("player input exceeds the 16,000 character limit")
        session = self.sessions.get(session_id)
        if session.world_id != self.world.config.id:
            raise ValueError("selected world ID does not match the session world")
        reindex_world(self.connection, self.world)
        state = self.game.state_for_session(session_id)
        context = ContextBuilder(self.connection, self.world).build(
            state, action, session.head_turn_id, self.summaries.latest(session_id)
        )
        request = self._request(context, self.world.config.model.temperature)
        first_id, first_response = self._generate(session_id, session.head_turn_id, 1, request)
        try:
            proposal, events, candidate = self._validate_proposal(first_response.content, state)
        except (ProposalValidationError, StateEventValidationError, StateInvariantError) as error:
            errors = _validation_errors(error)
            self._complete_failure(first_id, first_response, errors)
            if self.world.config.gameplay.maximum_repair_attempts == 0:
                return self._raise_failed_repair(errors)
            repair_request = self._repair_request(state, action, first_response.content, errors)
            repair_id, repair_response = self._generate(session_id, session.head_turn_id, 2, repair_request)
            try:
                proposal, events, candidate = self._validate_proposal(repair_response.content, state)
            except (ProposalValidationError, StateEventValidationError, StateInvariantError) as repair_error:
                repair_errors = _validation_errors(repair_error)
                self._complete_failure(repair_id, repair_response, repair_errors)
                return self._raise_failed_repair(repair_errors)
            return self._commit(session_id, session.head_turn_id, action, proposal, events, candidate, context, repair_id, repair_response)
        return self._commit(session_id, session.head_turn_id, action, proposal, events, candidate, context, first_id, first_response)

    def _request(self, context: ContextAssembly, temperature: float) -> ModelRequest:
        settings = self.world.config.model
        token = os.environ.get(settings.api_token_env) if settings.api_token_env else None
        messages = [ChatMessage(role=message.role, content=message.content) for message in context.messages]
        return ModelRequest(model=settings.name, messages=messages,
            temperature=temperature, max_output_tokens=settings.max_output_tokens,
            timeout_seconds=settings.timeout_seconds, api_token=token)

    def _generate(self, session_id: str, parent_turn_id: str | None, attempt: int, request: ModelRequest) -> tuple[str, ModelResponse]:
        request_json = canonical_json(request.audit_payload())
        request_hash = sha256_text(request_json)
        call_id = self._id_factory()
        with self.connection:
            self.model_calls.create(call_id, session_id, parent_turn_id, attempt, self.world.config.model.backend,
                request.model, request_hash, request_json=request_json if self.world.config.audit.store_prompts else None)
        return call_id, self.backend.generate(request)

    def _validate_proposal(self, content: str, state: GameState) -> tuple[TurnProposal, list[Event], GameState]:
        proposal = parse_turn_proposal(content)
        if len(proposal.events) > self.world.config.gameplay.maximum_events_per_turn:
            raise ProposalValidationError("model response exceeds the configured maximum event count")
        candidate = state
        events: list[Event] = []
        for event in proposal.events:
            # Small local models frequently restate an already-true change.
            # Do not spend the one repair attempt on an event that is safe and
            # provably unable to change authoritative state.
            if is_noop_event(candidate, event):
                continue
            committed = validate_event(candidate, event, self.world.config.gameplay, model_generated=True)
            # Relationship clamping can turn a nonzero proposed delta into a
            # no-op; omit that event as well so history reflects real changes.
            if is_noop_event(candidate, committed):
                continue
            candidate = apply_event(candidate, committed, self.world.config.gameplay)
            events.append(committed)
        return proposal, events, candidate

    def _repair_request(self, state: GameState, action: str, invalid: str, errors: list[str]) -> ModelRequest:
        error_text = "\n".join(f"{index}. {error}" for index, error in enumerate(errors, 1))[:8_000]
        content = "\n\n".join(("REPAIR REQUEST", self.world.repair_prompt, TURN_OUTPUT_CONTRACT, "ORIGINAL PLAYER ACTION\n" + action,
            "ORIGINAL INVALID RESPONSE\n" + invalid, "VALIDATION ERRORS\n" + error_text,
            "CURRENT STATE\n" + format_state(state)))
        settings = self.world.config.model
        token = os.environ.get(settings.api_token_env) if settings.api_token_env else None
        return ModelRequest(model=settings.name, messages=[ChatMessage(role="system", content=self.world.repair_prompt), ChatMessage(role="user", content=content)], temperature=0.2,
            max_output_tokens=settings.max_output_tokens, timeout_seconds=settings.timeout_seconds, api_token=token)

    def _complete_failure(self, call_id: str, response: ModelResponse, errors: list[str]) -> None:
        with self.connection:
            self.model_calls.complete(call_id, response_json=self._stored_response(response),
                response_hash=sha256_text(canonical_json(response.raw_response)),
                validation_errors_json=canonical_json({"errors": errors}), prompt_eval_count=response.prompt_eval_count,
                eval_count=response.eval_count, duration_ms=response.duration_ms)

    def _commit(self, session_id: str, parent_id: str | None, action: str, proposal: TurnProposal, events: list[Event], state: GameState, context: ContextAssembly, call_id: str, response: ModelResponse) -> TurnResult:
        completion = {"response_json": self._stored_response(response), "response_hash": sha256_text(canonical_json(response.raw_response)),
            "parsed_response_json": canonical_json(proposal.model_dump(mode="json")), "validation_errors_json": None,
            "prompt_eval_count": response.prompt_eval_count, "eval_count": response.eval_count, "duration_ms": response.duration_ms}
        turn = self.turns.commit(session_id, parent_id, self._id_factory(), action, proposal.narration, events, state,
            model_call_id=call_id, model_call_completion=completion)
        if turn.turn_number % 10 == 0:
            self._create_summary(session_id, turn)
        self.last_error = None
        return TurnResult(turn, state, proposal.narration, context)

    def _stored_response(self, response: ModelResponse) -> str | None:
        return canonical_json(response.raw_response) if self.world.config.audit.store_raw_model_responses else None

    def _create_summary(self, session_id: str, latest_turn: TurnRecord) -> None:
        turns = self.turns.ancestry(latest_turn.turn_id)
        text = "\n\n".join(f"TURN {turn.turn_number}\nPLAYER: {turn.player_input}\nNARRATOR: {turn.narration}" for turn in turns)
        heading = "EXTRACTIVE SCENE SUMMARY\n"
        content = heading + text[-(12_000 - len(heading)):]
        with self.connection:
            self.summaries.create(self._id_factory(), session_id, latest_turn.turn_id, content)

    def _raise_failed_repair(self, errors: list[str]) -> TurnResult:
        message = "The model response could not be validated; no turn was saved. Use /debug last-error for details."
        self.last_error = LastTurnError(message, errors)
        raise ProposalValidationError(message)


def _validation_errors(error: Exception) -> list[str]:
    return [str(error)[:8_000]]
