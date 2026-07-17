"""Deterministic, local lore query construction and scoring."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable

from ..state.models import GameState
from ..storage.repositories import LoreRepository
from .models import LoreMatch, StoredLoreDocument

_WORDS = re.compile(r"[^\W_]+", re.UNICODE)


def retrieval_terms(player_input: str, state: GameState, documents: Iterable[StoredLoreDocument]) -> list[str]:
    """Build bounded query terms from input and the active scene, without an LLM."""
    player = state.actors[state.player_actor_id]
    location = state.locations[player.location_id]
    active_actors = [actor for actor in state.actors.values() if actor.location_id == player.location_id]
    active_quests = [quest for quest in state.quests.values() if quest.status == "active"]
    source = [player_input, location.id, location.name]
    source.extend(value for actor in active_actors for value in (actor.id, actor.name))
    source.extend(value for quest in active_quests for value in (quest.id, quest.name))
    lowered_input = player_input.casefold()
    for document in documents:
        for alias in _strings(document.metadata.get("aliases")):
            if alias.casefold() in lowered_input:
                source.append(alias)
    terms: list[str] = []
    seen: set[str] = set()
    for word in _WORDS.findall(" ".join(source).casefold()):
        if len(word) == 1 and not word.isdigit():
            continue
        if word not in seen:
            seen.add(word)
            terms.append(word)
        if len(terms) == 40:
            break
    return terms


def fts_query(terms: Iterable[str]) -> str:
    return " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)


def retrieve_lore(connection: sqlite3.Connection, state: GameState, player_input: str, maximum: int) -> list[LoreMatch]:
    """Retrieve scored lore using FTS5 when available or fallback search."""
    repository = LoreRepository(connection)
    documents = repository.documents(state.world_id)
    terms = retrieval_terms(player_input, state, documents)
    fts_scores = repository.fts_candidates(state.world_id, fts_query(terms)) if repository.fts_available() else {}
    candidates = [document for document in documents if document.document_id in fts_scores] if fts_scores else documents
    matches = [LoreMatch(document, _score(document, state, player_input, set(terms), fts_scores.get(document.document_id))) for document in candidates]
    matches.sort(key=lambda match: (-match.score, match.document.document_id))
    return matches[:maximum]


def _score(document: StoredLoreDocument, state: GameState, player_input: str, terms: set[str], fts_score: float | None) -> float:
    metadata, entity_ids = document.metadata, set(_strings(document.metadata.get("entity_ids")))
    current_location = state.actors[state.player_actor_id].location_id
    active_actors = {actor.id for actor in state.actors.values() if actor.location_id == current_location}
    active_quests = {quest.id for quest in state.quests.values() if quest.status == "active"}
    aliases = _strings(metadata.get("aliases"))
    tag_matches = sum(1 for tag in _strings(metadata.get("tags")) if set(_WORDS.findall(tag.casefold())) & terms)
    fallback = len(set(_WORDS.findall(document.title.casefold())) & terms) * 4 + len(set(_WORDS.findall(document.body.casefold())) & terms)
    return ((100 if entity_ids & ({current_location} | active_actors | active_quests) else 0)
        + (80 if current_location in entity_ids else 0) + (60 if entity_ids & active_actors else 0)
        + (50 if entity_ids & active_quests else 0) + (40 if any(alias.casefold() in player_input.casefold() for alias in aliases) else 0)
        + tag_matches * 10 + float(metadata.get("priority", 0.5)) * 10 + fallback + (min(fts_score, 1.0) * 20 if fts_score is not None else 0))


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
