from __future__ import annotations

from typing import Any

from ptcgbench.agents.interfaces.schema import (
    AbilityInfo,
    AttackInfo,
    CardObservation,
    PlayerObservation,
    PokemonObservation,
    StateObservation,
)
from ptcg.core.action import AttachEnergyAction, EvolvePokemonAction, UseToolAction
from ptcg.core.card import Card, PokemonCard, ToolCard
from ptcg.core.enums import CardPosition, PlayerId
from ptcg.core.player import Player
from ptcg.core.state import State


class StateObserver:
    """Convert game state to LLM-friendly structured observation."""

    def observe(
        self,
        state: State,
        info: dict[str, Any],
        available_actions: list[Any] | None = None,
    ) -> StateObservation:
        my_player, opp_player = self._get_players(state)
        return StateObservation(
            turn=state.turn.name.lower() if state.turn else "none",
            turn_number=state.turn_number,
            timestep=state.timestep,
            my=self._build_player_obs(my_player, reveal_hand=True),
            opponent=self._build_player_obs(opp_player, reveal_hand=False),
            stadium=state.stadium[0].name if state.stadium else None,
            choosing_card=info.get("is_choosing_card", False),
            choosing_tips=self._get_choosing_tips(info),
            opponent_last_turn_actions=self._build_opponent_actions(info),
            available_actions=self._build_available_actions(available_actions or []),
        )

    def _get_players(self, state: State) -> tuple[Player, Player]:
        if state.turn == PlayerId.PLAYER1:
            return state.player1, state.player2
        return state.player2, state.player1

    def _get_choosing_tips(self, info: dict[str, Any]) -> str:
        if not info.get("is_choosing_card", False):
            return ""
        prompt = info.get("prompt")
        if prompt and getattr(prompt, "tips", ""):
            return prompt.tips
        return "Choose a card from the candidates."

    def _build_opponent_actions(self, info: dict[str, Any]) -> list[str]:
        actions = info.get("opponent_last_turn_actions", [])
        result = []
        for action in actions:
            action_info = action.to_nl()
            result.append(action_info)
        return result

    def _build_available_actions(self, actions: list[Any]) -> list[str]:
        result = []
        for action in actions:
            if isinstance(action, (EvolvePokemonAction, AttachEnergyAction, UseToolAction)):
                result.append(self._target_action_to_nl(action, actions))
            else:
                result.append(action.to_nl())
        return result

    def _target_action_to_nl(
        self,
        action: EvolvePokemonAction | AttachEnergyAction | UseToolAction,
        actions: list[Any],
    ) -> str:
        target = action.target
        target_str = self._target_card_str(target, actions, type(action), action.source)

        if isinstance(action, EvolvePokemonAction):
            position_str = {
                CardPosition.ACTIVE: "Active Spot",
                CardPosition.BENCH: "Bench",
            }.get(target.cardPosition, "Unknown")
            return (
                f"{action._player_str()} evolved [{target_str}] into "
                f"[{action.source.name}] in the {position_str}"
            )

        return f"{action._player_str()} attached [{action.source.name}] to [{target_str}]"

    def _target_card_str(
        self,
        target: Card,
        actions: list[Any],
        action_cls: type,
        source: Card,
    ) -> str:
        if not self._needs_target_index(target, actions, action_cls, source):
            return target.name
        return f"{target.name} index={target.index}"

    def _needs_target_index(
        self,
        target: Card,
        actions: list[Any],
        action_cls: type,
        source: Card,
    ) -> bool:
        if getattr(target, "cardPosition", None) not in (CardPosition.ACTIVE, CardPosition.BENCH):
            return False

        same_name_targets = [
            action.target
            for action in actions
            if isinstance(action, action_cls)
            and getattr(action, "source", None) is source
            and getattr(action.target, "name", None) == target.name
            and getattr(action.target, "cardPosition", None)
            in (CardPosition.ACTIVE, CardPosition.BENCH)
        ]
        return len({id(candidate) for candidate in same_name_targets}) > 1

    def _build_player_obs(self, player: Player, reveal_hand: bool) -> PlayerObservation:
        hand_cards = (
            [CardObservation(id=c.id, name=c.name) for c in player.hand] if reveal_hand else []
        )
        return PlayerObservation(
            active=[self._build_pokemon_obs(p) for p in player.active],
            bench=[self._build_pokemon_obs(p) for p in player.bench],
            hand=hand_cards,
            hand_count=len(player.hand),
            deck_count=len(player.left),
            prize_count=len(player.prize),
            discard=[CardObservation(id=c.id, name=c.name) for c in player.discard],
            discard_count=len(player.discard),
            energy_played=player.energyPlayedTurn,
            supporter_played=player.supporterPlayedTurn,
            retreated=player.retreatTurn,
        )

    def _build_pokemon_obs(self, card: PokemonCard) -> PokemonObservation:
        energy = [e.name for e in card.energy]
        tools = [c.name for c in card.attachment if isinstance(c, ToolCard)]
        # damage_counters is not declared in PokemonCard; it is set imperatively by
        # the damage-dealing logic at runtime, so getattr with default 0 is correct
        damage_counters = getattr(card, "damage_counters", 0)

        attacks = []
        # attacks and ability are class-level annotations only; card subclasses may not
        # assign them in __init__, so hasattr is required (same pattern as card.py itself)
        if hasattr(card, "attacks") and card.attacks:
            for atk in card.attacks:
                attacks.append(
                    AttackInfo(
                        name=atk.name if atk.name is not None else "",
                        damage=atk.damage if atk.damage is not None else 0,
                        cost=[c.name for c in (atk.cost or [])],
                        text=atk.text if atk.text is not None else "",
                    )
                )

        abilities = []
        # same reason as attacks above
        if hasattr(card, "ability") and card.ability:
            for ab in card.ability:
                abilities.append(
                    AbilityInfo(
                        name=ab.name or "",
                        ability_type=ab.abilityType.name if ab.abilityType else "",
                        text=ab.text or "",
                    )
                )

        return PokemonObservation(
            id=card.id,
            name=card.name,
            hp=card.hp,
            damage_counters=damage_counters,
            card_type=card.cardType.name if card.cardType else "",
            stage=card.stage.name if card.stage else "",
            pokemon_type=card.pokemonType.name if card.pokemonType else "",
            retreat_cost=[c.name for c in (card.retreat or [])],
            energy=energy,
            tools=tools,
            attacks=attacks,
            abilities=abilities,
            prize=card.prize,
        )
