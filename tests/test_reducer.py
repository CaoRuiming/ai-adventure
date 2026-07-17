"""Deterministic tests for authoritative runtime state and reducers."""

from __future__ import annotations

import unittest
from pathlib import Path

from local_adventure.content.loader import load_world
from local_adventure.errors import StateEventValidationError, StateInvariantError
from local_adventure.state.events import (
    AdjustRelationshipEvent,
    AdjustStatEvent,
    MoveActorEvent,
    SetFlagEvent,
    SetQuestStatusEvent,
    TransferItemEvent,
)
from local_adventure.state.models import GameState, build_initial_state, state_projection
from local_adventure.state.reducer import apply_event, apply_events
from local_adventure.state.validator import validate_event, validate_state


SAMPLE_WORLD = Path(__file__).parents[1] / "worlds" / "ember_hollow"


class ReducerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = load_world(SAMPLE_WORLD)
        self.settings = self.world.config.gameplay
        self.state = build_initial_state(self.world)

    def valid(self, event: object):
        return validate_event(self.state, event, self.settings)

    def test_initial_state_is_canonical_and_deterministic(self) -> None:
        repeated = build_initial_state(self.world)
        self.assertEqual(self.state.canonical_json(), repeated.canonical_json())
        self.assertEqual(self.state.player_actor_id, "player")
        self.assertEqual(self.state.items["brass_key"].holder_id, "mark")

    def test_move_actor(self) -> None:
        event = self.valid(MoveActorEvent(type="move_actor", actor_id="player", location_id="west_gate", reason="Walks west."))
        updated = apply_event(self.state, event, self.settings)
        self.assertEqual(updated.actors["player"].location_id, "west_gate")
        self.assertEqual(self.state.actors["player"].location_id, "observatory")

    def test_transfer_item(self) -> None:
        event = self.valid(TransferItemEvent(type="transfer_item", item_id="brass_key", holder_type="actor", holder_id="player", reason="Mark gives it."))
        self.assertEqual(apply_event(self.state, event, self.settings).items["brass_key"].holder_id, "player")

    def test_set_flag(self) -> None:
        event = self.valid(SetFlagEvent(type="set_flag", key="gate_open", value=True, reason="The lock opens."))
        self.assertTrue(apply_event(self.state, event, self.settings).flags["gate_open"])

    def test_adjust_stat(self) -> None:
        event = self.valid(AdjustStatEvent(type="adjust_stat", actor_id="player", stat="health", delta=-2, reason="Debris falls."))
        self.assertEqual(apply_event(self.state, event, self.settings).actors["player"].stats["health"], 8)

    def test_adjust_relationship_clamps_and_records_applied_delta(self) -> None:
        data = self.state.model_dump(mode="python")
        data["actors"]["mark"]["relationships"]["player"]["trust"] = 99
        near_maximum = GameState.model_validate(data)
        event = AdjustRelationshipEvent(type="adjust_relationship", source_actor_id="mark", target_actor_id="player", dimension="trust", delta=20, reason="Trust grows.")
        normalized = validate_event(near_maximum, event, self.settings)
        self.assertEqual(normalized.applied_delta, 1)
        self.assertEqual(apply_event(near_maximum, normalized, self.settings).actors["mark"].relationships["player"]["trust"], 100)

    def test_set_quest_status(self) -> None:
        event = self.valid(SetQuestStatusEvent(type="set_quest_status", quest_id="west_gate", status="active", reason="The quest begins."))
        self.assertEqual(apply_event(self.state, event, self.settings).quests["west_gate"].status, "active")

    def test_invalid_entity_and_delta_are_rejected(self) -> None:
        with self.assertRaisesRegex(StateEventValidationError, "does not exist"):
            self.valid(MoveActorEvent(type="move_actor", actor_id="missing", location_id="west_gate", reason="Invalid."))
        with self.assertRaisesRegex(StateEventValidationError, "exceeds configured limit"):
            self.valid(AdjustStatEvent(type="adjust_stat", actor_id="player", stat="health", delta=21, reason="Invalid."))

    def test_model_cannot_allow_unconnected_move(self) -> None:
        event = MoveActorEvent(type="move_actor", actor_id="player", location_id="west_gate", allow_unconnected=True, reason="Administrative move.")
        with self.assertRaisesRegex(StateEventValidationError, "not permitted"):
            validate_event(self.state, event, self.settings)
        self.assertIs(validate_event(self.state, event, self.settings, model_generated=False), event)

    def test_input_is_not_mutated_and_repeated_application_is_equal(self) -> None:
        event = self.valid(SetFlagEvent(type="set_flag", key="heard_mark", value="yes", reason="Mark speaks."))
        original = self.state.canonical_json()
        first = apply_event(self.state, event, self.settings)
        second = apply_event(self.state, event, self.settings)
        self.assertEqual(self.state.canonical_json(), original)
        self.assertEqual(first, second)
        events = [
            self.valid(TransferItemEvent(type="transfer_item", item_id="brass_key", holder_type="actor", holder_id="player", reason="Mark gives it.")),
            self.valid(SetFlagEvent(type="set_flag", key="has_key", value=True, reason="Key received.")),
        ]
        self.assertEqual(apply_events(self.state, events, self.settings), apply_events(self.state, events, self.settings))

    def test_invariant_failure_is_typed(self) -> None:
        data = self.state.model_dump(mode="python")
        data["actors"]["player"]["location_id"] = "missing"
        with self.assertRaisesRegex(StateInvariantError, "missing location"):
            validate_state(GameState.model_validate(data), self.settings)

    def test_projection_is_readable_and_stable(self) -> None:
        projection = state_projection(self.state)
        self.assertEqual(projection["location"]["id"], "observatory")
        self.assertEqual(projection["valid_ids"]["actors"], ["mark", "player"])
        self.assertEqual(projection["visible_items"], ["brass_key"])
