"""Human-readable, privacy-safe exports of authoritative session history."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..app.game_service import GameService
from ..content.models import LoadedWorld
from ..errors import ConfigurationError
from ..state.events import (
    AdjustRelationshipEvent,
    AdjustStatEvent,
    MoveActorEvent,
    SetFlagEvent,
    SetQuestStatusEvent,
    TransferItemEvent,
)
from ..storage.repositories import CheckpointRepository, SessionRepository, TurnRecord, TurnRepository
from ..util.clocks import utc_now


@dataclass(frozen=True)
class SessionExport:
    """The rendered contents and source metadata for one export."""

    format: str
    content: str


class SessionExporter:
    """Build exports from authoritative state without exposing model-call audits."""

    def __init__(self, connection: sqlite3.Connection, world: LoadedWorld) -> None:
        self.connection = connection
        self.world = world
        self.sessions = SessionRepository(connection)
        self.turns = TurnRepository(connection)
        self.checkpoints = CheckpointRepository(connection)
        self.game = GameService(connection, world)

    def render_markdown(self, session_id: str) -> SessionExport:
        """Render the current session path as a structurally safe Markdown transcript."""
        session = self.sessions.get(session_id)
        turns = self.turns.ancestry(session.head_turn_id)
        scenario = self.world.scenarios[session.scenario_id]
        lines = [
            f"# {_plain_text(session.name)}",
            "",
            f"- World: {_plain_text(self.world.config.title)}",
            f"- Scenario: {_plain_text(scenario.title)}",
            f"- Session ID: `{session.session_id}`",
            f"- Exported: {utc_now()}",
            f"- Current turn: {turns[-1].turn_number if turns else 0}",
            "",
            "## Opening",
            "",
            _blockquote(scenario.opening_narration),
        ]
        for turn in turns:
            lines.extend(["", f"## Turn {turn.turn_number}", "", "**Player**", "", _blockquote(turn.player_input), "", "**Narrator**", "", _blockquote(turn.narration)])
            events = self.turns.events_for_turn(turn.turn_id)
            if events:
                lines.extend(["", "**State changes**", ""])
                lines.extend(f"- {_event_description(event, self.world)}" for event in events)
        state_json = json.dumps(self.game.state_for_session(session_id).model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2)
        fence = _code_fence(state_json)
        lines.extend(["", "## Current State", "", f"{fence}json", state_json, fence, ""])
        return SessionExport("markdown", "\n".join(lines))

    def render_json(self, session_id: str) -> SessionExport:
        """Render an interoperable JSON export without prompts or raw model responses."""
        session = self.sessions.get(session_id)
        turns = self.turns.ancestry(session.head_turn_id)
        payload = {
            "export_schema_version": 1,
            "session": {
                "session_id": session.session_id,
                "name": session.name,
                "world_id": session.world_id,
                "scenario_id": session.scenario_id,
                "head_turn_id": session.head_turn_id,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            },
            "world": {"id": self.world.config.id, "title": self.world.config.title, "source_path": self.world.root},
            "opening_narration": self.world.scenarios[session.scenario_id].opening_narration,
            "turns": [self._turn_payload(turn) for turn in turns],
            "current_state": self.game.state_for_session(session_id).model_dump(mode="json"),
            "checkpoints": [checkpoint.__dict__ for checkpoint in self.checkpoints.list_for_session(session_id)],
        }
        return SessionExport("json", json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")

    def write(self, session_id: str, export_format: str, output_path: Path) -> SessionExport:
        """Render and write one export, rejecting directory targets before mutation."""
        if output_path.exists() and output_path.is_dir():
            raise ConfigurationError(f"export path is a directory: {output_path}")
        if export_format == "markdown":
            exported = self.render_markdown(session_id)
        elif export_format == "json":
            exported = self.render_json(session_id)
        else:
            raise ConfigurationError(f"unsupported export format: {export_format}")
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(exported.content, encoding="utf-8", newline="\n")
        except OSError as error:
            raise ConfigurationError(f"unable to write export '{output_path}': {error}") from error
        return exported

    def _turn_payload(self, turn: TurnRecord) -> dict[str, object]:
        return {
            "turn_id": turn.turn_id,
            "parent_turn_id": turn.parent_turn_id,
            "turn_number": turn.turn_number,
            "player_input": turn.player_input,
            "narration": turn.narration,
            "status": turn.status,
            "created_at": turn.created_at,
            "events": [event.model_dump(mode="json") for event in self.turns.events_for_turn(turn.turn_id)],
        }


def _blockquote(content: str) -> str:
    """Quote untrusted transcript text so it cannot introduce Markdown headings."""
    return "\n".join(">" if not line else f"> {line}" for line in content.splitlines()) or ">"


def _code_fence(content: str) -> str:
    """Choose a fence longer than any backtick run in the included JSON."""
    longest = max((len(run.group()) for run in re.finditer(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def _plain_text(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")


def _event_description(event: object, world: LoadedWorld) -> str:
    if isinstance(event, MoveActorEvent):
        return f"{world.actors[event.actor_id].name} moved to {world.locations[event.location_id].name}."
    if isinstance(event, TransferItemEvent):
        item = world.items[event.item_id].name
        if event.holder_type == "none":
            return f"{item} no longer has a holder."
        holder = world.actors[event.holder_id].name if event.holder_type == "actor" else world.locations[event.holder_id].name
        return f"{item} was transferred to {holder}."
    if isinstance(event, SetFlagEvent):
        return f"Flag `{event.key}` was set to `{event.value}`."
    if isinstance(event, AdjustStatEvent):
        return f"{world.actors[event.actor_id].name}'s {event.stat} changed by {event.delta:+}."
    if isinstance(event, AdjustRelationshipEvent):
        return f"{world.actors[event.source_actor_id].name}'s {event.dimension} toward {world.actors[event.target_actor_id].name} changed by {event.applied_delta if event.applied_delta is not None else event.delta:+}."
    if isinstance(event, SetQuestStatusEvent):
        return f"Quest {world.quests[event.quest_id].name} is now {event.status}."
    return "State changed."
