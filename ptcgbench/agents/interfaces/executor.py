from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from ptcgbench.agents.tools.tool_schemas import TOOL_TO_ACTION_TYPE
from ptcg.core.action import (
    Action,
    AttachEnergyAction,
    AttackAction,
    ChooseCardAction,
    EvolvePokemonAction,
    PlayPokemonAction,
    RetreatAction,
    UseToolAction,
)


@dataclass
class MatchResult:
    action: Action | None
    level: str
    reason: str


class ToolCallExecutor:
    """Map LLM tool_call to a real Action from raw_available_actions."""

    def execute(
        self, tool_name: str, arguments: dict[str, Any], info: dict[str, Any]
    ) -> MatchResult:
        action_type = TOOL_TO_ACTION_TYPE.get(tool_name)
        if not action_type:
            return MatchResult(
                action=None,
                level="NONE",
                reason=f"Unknown tool name: {tool_name}",
            )

        available: list[Action] = info["raw_available_actions"]
        if not available:
            raise ValueError("No available actions to execute")

        available_types = sorted({a.actionType.name for a in available})
        type_filtered = self._filter_by_type(available, action_type)
        if not type_filtered:
            reason = (
                f"Action type {action_type!r} is not available. "
                f"Available types: {available_types}. "
            )
            return MatchResult(action=None, level="NONE", reason=reason)

        if action_type == "CHOOSE_CARD_ACTION":
            return self._match_choose_card(type_filtered, arguments)

        if action_type == "PASS_TURN":
            return MatchResult(action=type_filtered[0], level="FULL", reason="")

        source_card = arguments.get("source_card", "")
        after_source, source_hit = self._filter_by_source(type_filtered, source_card)
        candidates, extra_hit = self._filter_by_extra(after_source, tool_name, arguments)

        if candidates:
            if source_hit and extra_hit:
                return MatchResult(action=candidates[0], level="FULL", reason="")
            parts = []
            if not source_hit:
                parts.append(
                    f"source_card {source_card!r} not found among "
                    f"{[a.to_nl() for a in type_filtered]}"
                )
            if not extra_hit:
                parts.append(self._extra_mismatch_reason(tool_name, arguments))
            level = "PARTIAL" if (source_hit or extra_hit) else "TYPE_ONLY"
            reason = f"{action_type} partial match — " + "; ".join(parts)
            return MatchResult(action=None, level=level, reason=reason)

        reason = (
            f"No actions remained after filtering by type={action_type!r}, "
            f"source={source_card!r}, extra fields. "
        )
        return MatchResult(action=None, level="NONE", reason=reason)

    def _extra_mismatch_reason(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if tool_name == "attack":
            attack_name = arguments.get("attack_name", "")
            return f"attack_name {attack_name!r} not found"
        if tool_name == "play_pokemon":
            position = arguments.get("position", "")
            return f"position {position!r} not found"
        if tool_name in ("evolve_pokemon", "attach_energy", "use_tool"):
            target_card = arguments.get("target_card", "")
            target_index = arguments.get("target_index")
            if target_index is not None:
                return f"target_card {target_card!r} with target_index {target_index!r} not found"
            return f"target_card {target_card!r} not found"
        return "extra field mismatch"

    def _filter_by_type(self, actions: list[Action], action_type: str) -> list[Action]:
        filtered = [a for a in actions if a.actionType.name == action_type]
        return filtered if filtered else []

    def _filter_by_source(
        self, actions: list[Action], source_card: str
    ) -> tuple[list[Action], bool]:
        if not source_card:
            return actions, False
        filtered = []
        for a in actions:
            if isinstance(a, RetreatAction):
                if hasattr(a, "active_pokemon") and a.active_pokemon.name == source_card:
                    filtered.append(a)
            elif (
                hasattr(a, "source") and hasattr(a.source, "name") and a.source.name == source_card
            ):
                filtered.append(a)
        if filtered:
            return filtered, True
        return actions, False

    def _filter_by_extra(
        self, actions: list[Action], tool_name: str, arguments: dict[str, Any]
    ) -> tuple[list[Action], bool]:
        if not actions:
            return actions, False

        if tool_name == "attack":
            attack_name = arguments.get("attack_name", "")
            if attack_name:
                filtered = [
                    a
                    for a in actions
                    if isinstance(a, AttackAction) and a.attack.name == attack_name
                ]
                if filtered:
                    return filtered, True
                return actions, False

        if tool_name == "play_pokemon":
            position = arguments.get("position", "")
            if position:
                filtered = [
                    a
                    for a in actions
                    if isinstance(a, PlayPokemonAction) and a.position.name == position
                ]
                if filtered:
                    return filtered, True
                return actions, False

        if tool_name == "evolve_pokemon":
            target_card = arguments.get("target_card", "")
            if target_card:
                filtered = [
                    a
                    for a in actions
                    if isinstance(a, EvolvePokemonAction)
                    and hasattr(a.target, "name")
                    and a.target.name == target_card
                ]
                filtered = self._filter_by_target_index(filtered, arguments)
                if filtered:
                    return filtered, True
                return actions, False

        if tool_name == "attach_energy":
            target_card = arguments.get("target_card", "")
            if target_card:
                filtered = [
                    a
                    for a in actions
                    if isinstance(a, AttachEnergyAction)
                    and hasattr(a.target, "name")
                    and a.target.name == target_card
                ]
                filtered = self._filter_by_target_index(filtered, arguments)
                if filtered:
                    return filtered, True
                return actions, False

        if tool_name == "use_tool":
            target_card = arguments.get("target_card", "")
            if target_card:
                filtered = [
                    a
                    for a in actions
                    if isinstance(a, UseToolAction)
                    and hasattr(a.target, "name")
                    and a.target.name == target_card
                ]
                filtered = self._filter_by_target_index(filtered, arguments)
                if filtered:
                    return filtered, True
                return actions, False

        return actions, True

    def _filter_by_target_index(
        self, actions: list[Action], arguments: dict[str, Any]
    ) -> list[Action]:
        target_index = arguments.get("target_index")
        if target_index is None:
            return actions
        if not isinstance(target_index, int):
            return []
        return [
            a
            for a in actions
            if hasattr(a, "target") and getattr(a.target, "index", None) == target_index
        ]

    def _match_choose_card(self, actions: list[Action], arguments: dict[str, Any]) -> MatchResult:
        chosen_cards = arguments.get("chosen_cards", [])
        chosen_indices = arguments.get("chosen_indices")

        if chosen_indices is not None:
            if not isinstance(chosen_indices, list) or not all(
                isinstance(i, int) for i in chosen_indices
            ):
                return MatchResult(
                    action=None,
                    level="PARTIAL",
                    reason=(
                        "CHOOSE_CARD_ACTION: chosen_indices must be a list of integers, "
                        f"got {chosen_indices!r}."
                    ),
                )

        if chosen_indices:
            target_indices = Counter(chosen_indices)
            matched_by_indices = [
                a
                for a in actions
                if isinstance(a, ChooseCardAction)
                and len(a.choose_field_indices()) == len(chosen_indices)
                and Counter(a.choose_field_indices()) == target_indices
            ]
            if matched_by_indices:
                return MatchResult(action=matched_by_indices[0], level="FULL", reason="")

            return MatchResult(
                action=None,
                level="PARTIAL",
                reason=(
                    f"CHOOSE_CARD_ACTION: requested field indices {chosen_indices!r} "
                    f"did not match any available choice. "
                    f"Available choices: {[a.to_nl() for a in actions]}. "
                ),
            )

        # Hidden cards — any choice is valid, pick the first one
        if actions and isinstance(actions[0], ChooseCardAction) and actions[0].hidden:
            return MatchResult(action=actions[0], level="FULL", reason="")

        target_counter = Counter(chosen_cards)

        matched = [
            a
            for a in actions
            if isinstance(a, ChooseCardAction)
            and Counter(c.name for c in a.chosen) == target_counter
        ]
        if matched:
            return MatchResult(action=matched[0], level="FULL", reason="")

        reason = (
            f"CHOOSE_CARD_ACTION: requested cards {chosen_cards!r} "
            f"did not match any available choice. "
            f"Available choices: {[a.to_nl() for a in actions]}. "
        )
        return MatchResult(action=None, level="PARTIAL", reason=reason)
