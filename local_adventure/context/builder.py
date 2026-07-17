"""Deterministic two-message context assembly, with explicit diagnostics."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..content.models import LoadedWorld, PromptSkill
from ..errors import ContextBudgetError
from ..lore.query import retrieve_lore
from ..state.models import GameState
from ..storage.repositories import TurnRepository
from ..util.hashing import sha256_text
from .budget import join_sections
from .formatter import format_lore, format_state, format_turn, truncate_paragraphs

TURN_OUTPUT_CONTRACT = """OUTPUT FORMAT
Reply with exactly one JSON object and no Markdown or explanation. Its required shape is {\"narration\": \"...\", \"events\": [...]}. `narration` must be non-empty. Use an empty `events` list when no mechanical change occurs. Every event needs a non-empty `reason` and one of these forms, using only IDs from the supplied state:
- {\"type\":\"move_actor\",\"actor_id\":\"...\",\"location_id\":\"...\",\"reason\":\"...\"}
- {\"type\":\"transfer_item\",\"item_id\":\"...\",\"holder_type\":\"actor|location|none\",\"holder_id\":\"...\",\"reason\":\"...\"}
- {\"type\":\"set_flag\",\"key\":\"...\",\"value\":true,\"reason\":\"...\"}
- {\"type\":\"adjust_stat\",\"actor_id\":\"...\",\"stat\":\"...\",\"delta\":1,\"reason\":\"...\"}
- {\"type\":\"adjust_relationship\",\"source_actor_id\":\"...\",\"target_actor_id\":\"...\",\"dimension\":\"...\",\"delta\":1,\"reason\":\"...\"}
- {\"type\":\"set_quest_status\",\"quest_id\":\"...\",\"status\":\"...\",\"reason\":\"...\"}"""


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ContextDiagnostics:
    total_chars: int
    section_chars: dict[str, int]
    lore: list[tuple[str, float]]
    skill_ids: list[str]
    turn_numbers: list[int]
    omitted_lore_count: int
    omitted_skill_count: int
    omitted_turn_count: int
    request_hash: str
    raw_prompts_stored: bool


@dataclass(frozen=True)
class ContextAssembly:
    messages: list[ChatMessage]
    diagnostics: ContextDiagnostics


class ContextBuilder:
    """Build context from content, state, history, and local retrieval only."""

    def __init__(self, connection: sqlite3.Connection, world: LoadedWorld) -> None:
        self.connection, self.world, self.turns = connection, world, TurnRepository(connection)

    def build(self, state: GameState, player_input: str, head_turn_id: str | None = None, summary: str = "") -> ContextAssembly:
        if len(player_input) > 16_000:
            raise ValueError("player input exceeds the 16,000 character limit")
        config = self.world.config.context
        system_sections = [self.world.world_markdown, self.world.narrator_prompt, *self.world.rules, TURN_OUTPUT_CONTRACT]
        system = join_sections(system_sections)
        state_text = format_state(state)
        if len(system) > config.system_chars:
            raise ContextBudgetError("mandatory system content exceeds system_chars")
        if len(state_text) > config.state_chars:
            raise ContextBudgetError("state projection exceeds state_chars")
        if len(system) + len(state_text) + len(player_input) > config.max_chars:
            raise ContextBudgetError("mandatory system content, state, and player input exceed max_chars")

        selected_skills, omitted_skills = _select_skills(self.world.skills, state, player_input, config.maximum_skills, config.skills_chars)
        skill_text = join_sections(_format_skill(skill) for skill in selected_skills)
        lore_matches = retrieve_lore(self.connection, state, player_input, config.maximum_lore_documents)
        lore_text, included_lore, omitted_lore = _format_lore(lore_matches, config.lore_chars)
        recent_text, included_turns, omitted_turns = self._recent_turns(head_turn_id, config.maximum_recent_turns, config.recent_turns_chars)
        user_sections = [state_text, skill_text, lore_text]
        if summary:
            user_sections.append("SUMMARY\n" + summary)
        if omitted_turns:
            user_sections.append("[Older history omitted due to context budget.]")
        user_sections.extend([recent_text, "PLAYER INPUT\n" + player_input])
        user = join_sections(user_sections)
        # Section caps alone leave room for input, but summaries can consume it.
        if len(system) + len(user) > config.max_chars:
            raise ContextBudgetError("assembled context exceeds max_chars")
        messages = [ChatMessage("system", system), ChatMessage("user", user)]
        section_chars = {"system": len(system), "state": len(state_text), "skills": len(skill_text), "lore": len(lore_text), "recent_turns": len(recent_text), "player_input": len(player_input)}
        request_hash = sha256_text("\n\x00\n".join(message.role + "\n" + message.content for message in messages))
        return ContextAssembly(messages, ContextDiagnostics(len(system) + len(user), section_chars,
            [(match.document.relative_path, match.score) for match in included_lore], [skill.config.id for skill in selected_skills],
            included_turns, omitted_lore, omitted_skills, omitted_turns, request_hash, self.world.config.audit.store_prompts))

    def _recent_turns(self, head_turn_id: str | None, maximum_turns: int, budget: int) -> tuple[str, list[int], int]:
        turns = self.turns.ancestry(head_turn_id)[-maximum_turns:] if head_turn_id else []
        selected: list[str] = []
        numbers: list[int] = []
        for turn in reversed(turns):
            rendered = format_turn(turn, self.turns.events_for_turn(turn.turn_id), budget)
            if len(join_sections([rendered, *selected])) > budget:
                break
            selected.insert(0, rendered)
            numbers.insert(0, turn.turn_number)
        return join_sections(selected), numbers, len(turns) - len(selected)


def _select_skills(skills: list[PromptSkill], state: GameState, player_input: str, maximum: int, budget: int) -> tuple[list[PromptSkill], int]:
    active_ids = {actor.id for actor in state.actors.values() if actor.location_id == state.actors[state.player_actor_id].location_id}
    lowered = player_input.casefold()
    scored: list[tuple[tuple[float, float, float, float, str], PromptSkill]] = []
    for skill in skills:
        entity_matches = len(active_ids & set(skill.config.entity_ids))
        trigger_matches = sum(term.casefold() in lowered for term in skill.config.trigger_terms)
        if skill.config.always_include or entity_matches or trigger_matches:
            scored.append(((-int(skill.config.always_include), -entity_matches, -trigger_matches, -skill.config.priority, skill.config.id), skill))
    scored.sort(key=lambda item: item[0])
    candidates = [skill for _, skill in scored[:maximum]]
    included: list[PromptSkill] = []
    for skill in candidates:
        rendered = _format_skill(skill)
        if len(join_sections([*(_format_skill(value) for value in included), rendered])) <= budget:
            included.append(skill)
    return included, len(candidates) - len(included) + max(0, len(scored) - maximum)


def _format_skill(skill: PromptSkill) -> str:
    return f"--- SKILL: {skill.config.name} [{skill.config.id}] ---\n" + truncate_paragraphs(skill.instructions, skill.config.maximum_chars) + "\n--- END SKILL ---"


def _format_lore(matches: list[object], budget: int) -> tuple[str, list[object], int]:
    included: list[object] = []
    sections: list[str] = []
    for match in matches:
        rendered = format_lore(match, budget)
        if len(join_sections([*sections, rendered])) > budget:
            continue
        sections.append(rendered)
        included.append(match)
    return join_sections(sections), included, len(matches) - len(included)
