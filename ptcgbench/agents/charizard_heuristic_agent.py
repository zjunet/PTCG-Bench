"""Fixed heuristic agent tuned for the bundled Charizard ex deck."""

from __future__ import annotations

import random
from typing import Any

from ptcgbench.agents.base_agent import BaseAgent
from ptcg.core.action import (
    Action,
    AttachEnergyAction,
    AttackAction,
    ChooseCardAction,
    EvolvePokemonAction,
    PassTurn,
    PlayPokemonAction,
    PutStadiumAction,
    RetreatAction,
    UseAbilityAction,
    UseItemAction,
    UseStadiumAction,
    UseSupporterAction,
    UseToolAction,
)
from ptcg.core.enums import PlayerId, PokemonPosition
from ptcg.core.state import State


SETUP_POKEMON = {
    "Charmander": 120,
    "Pidgey": 105,
    "Bidoof": 70,
    "Cleffa": 55,
    "Rotom V": 50,
    "Manaphy": 35,
    "Jirachi": 30,
}

SEARCH_TARGETS = {
    "Charizard ex": 130,
    "Pidgeot ex": 115,
    "Charmander": 110,
    "Pidgey": 95,
    "Rare Candy": 90,
    "Buddy-Buddy Poffin": 82,
    "Ultra Ball": 75,
    "Arven": 72,
    "Basic Fire Energy": 62,
    "Fire Energy": 62,
    "Boss's Orders": 45,
    "Counter Catcher": 45,
    "Prime Catcher": 45,
}

DISCARD_KEEP_PRIORITY = {
    "Charizard ex": 100,
    "Rare Candy": 95,
    "Charmander": 92,
    "Pidgeot ex": 90,
    "Pidgey": 82,
    "Arven": 78,
    "Buddy-Buddy Poffin": 76,
    "Ultra Ball": 62,
    "Boss's Orders": 58,
    "Counter Catcher": 56,
    "Prime Catcher": 56,
    "Basic Fire Energy": 52,
    "Fire Energy": 52,
    "Super Rod": 45,
    "Radiant Charizard": 42,
    "Iono": 40,
    "Professor Turo's Scenario": 35,
    "Lost Vacuum": 24,
    "Collapsed Stadium": 20,
    "Defiance Band": 18,
    "Forest Seal Stone": 18,
    "Mist Energy": 15,
}


class CharizardHeuristicAgent(BaseAgent):
    """Pure rule-based policy for Charizard ex / Pidgeot ex.

    The agent never samples outside the environment's legal action list. It
    assigns deterministic scores to legal actions and uses seeded randomness
    only to break exact ties.
    """

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def predict(self, obs: State, info: dict[str, Any]) -> Action:
        actions = info.get("raw_available_actions", [])
        if not actions:
            raise ValueError("No available actions to choose from")

        if info.get("is_choosing_card") or isinstance(actions[0], ChooseCardAction):
            return self._best(actions, lambda action: self._score_choice(action, info, obs))

        return self._best(actions, lambda action: self._score_game_action(action, obs))

    def _best(self, actions: list[Action], score_fn) -> Action:
        scored = [(score_fn(action), self.rng.random(), action) for action in actions]
        return max(scored, key=lambda item: (item[0], item[1]))[2]

    def _score_game_action(self, action: Action, state: State) -> float:
        source_name = self._name(getattr(action, "source", None))

        if isinstance(action, AttackAction):
            return self._score_attack(action, state)

        if isinstance(action, EvolvePokemonAction):
            return self._score_evolution(action)

        if isinstance(action, UseAbilityAction):
            ability_name = self._name(getattr(action, "ability", None))
            if source_name == "Pidgeot ex" and ability_name == "Quick Search":
                return 790
            if source_name == "Rotom V" and ability_name == "Instant Charge":
                return 360
            return 300

        if isinstance(action, UseItemAction):
            return self._score_item(action, state)

        if isinstance(action, UseSupporterAction):
            return self._score_supporter(action, state)

        if isinstance(action, AttachEnergyAction):
            return self._score_energy_attachment(action)

        if isinstance(action, PlayPokemonAction):
            return self._score_play_pokemon(action)

        if isinstance(action, UseToolAction):
            target_name = self._name(getattr(action, "target", None))
            if source_name == "Defiance Band" and target_name in {
                "Charizard ex",
                "Radiant Charizard",
            }:
                return 420
            return 120

        if isinstance(action, RetreatAction):
            return self._score_retreat(action)

        if isinstance(action, (PutStadiumAction, UseStadiumAction)):
            return 80

        if isinstance(action, PassTurn):
            return -1000

        return 0

    def _score_attack(self, action: AttackAction, state: State) -> float:
        source_name = self._name(action.source)
        target = action.target
        target_hp = getattr(target, "hp", 0)
        damage = getattr(action.attack, "damage", 0)
        score = 500 + damage

        if source_name == "Charizard ex":
            score += 260
        elif source_name == "Radiant Charizard":
            score += 170
        elif source_name == "Pidgeot ex":
            score += 70
        elif source_name in {"Cleffa", "Rotom V"}:
            score += 35

        if damage >= target_hp:
            score += 500 + 120 * getattr(target, "prize", 1)

        opponent = self._opponent(state, action.playerId)
        if opponent and target in opponent.bench:
            score += 120

        return score

    def _score_evolution(self, action: EvolvePokemonAction) -> float:
        source_name = self._name(action.source)
        target_name = self._name(action.target)
        if source_name == "Charizard ex":
            return 880 + (50 if target_name == "Charmander" else 0)
        if source_name == "Pidgeot ex":
            return 820
        if source_name == "Bibarel":
            return 520
        if source_name == "Charmeleon":
            return 430
        return 300

    def _score_item(self, action: UseItemAction, state: State) -> float:
        name = self._name(action.source)
        if name == "Rare Candy":
            return 840
        if name == "Buddy-Buddy Poffin":
            return 760
        if name == "Ultra Ball":
            return 690
        if name == "Nest Ball":
            return 620
        if name in {"Prime Catcher", "Counter Catcher"}:
            return 735 if self._has_ready_attacker(state, action.playerId) else 210
        if name == "Super Rod":
            return 160
        if name == "Lost Vacuum":
            return 130
        return 220

    def _score_supporter(self, action: UseSupporterAction, state: State) -> float:
        name = self._name(action.source)
        if name == "Arven":
            return 780
        if name == "Boss's Orders":
            return 730 if self._has_ready_attacker(state, action.playerId) else 260
        if name == "Iono":
            player = self._player(state, action.playerId)
            hand_size = len(player.hand) if player else 0
            return 650 if hand_size <= 3 else 240
        if name == "Professor Turo's Scenario":
            return 180
        return 250

    def _score_energy_attachment(self, action: AttachEnergyAction) -> float:
        target_name = self._name(action.target)
        attached = len(getattr(action.target, "energy", []))
        if target_name == "Charizard ex":
            return 700 - 20 * attached
        if target_name == "Radiant Charizard":
            return 610 - 15 * attached
        if target_name == "Charmander":
            return 520 - 15 * attached
        if target_name == "Pidgeot ex":
            return 260
        return 120

    def _score_play_pokemon(self, action: PlayPokemonAction) -> float:
        name = self._name(action.source)
        if action.position == PokemonPosition.ACTIVE:
            active_priority = {
                "Cleffa": 220,
                "Rotom V": 210,
                "Charmander": 200,
                "Pidgey": 90,
            }
            return active_priority.get(name, 60)

        score = 450 + SETUP_POKEMON.get(name, 0)
        if name in {"Lumineon V", "Rotom V"}:
            score -= 80
        return score

    def _score_retreat(self, action: RetreatAction) -> float:
        active_name = self._name(getattr(action, "active_pokemon", None))
        if active_name in {"Cleffa", "Rotom V", "Pidgey", "Bidoof"}:
            return 410
        return 60

    def _score_choice(self, action: ChooseCardAction, info: dict[str, Any], state: State) -> float:
        prompt = info.get("prompt")
        source_name = self._name(getattr(prompt, "source", None))
        tips = getattr(prompt, "tips", "")

        if source_name == "Ultra Ball" and "discard" in tips:
            return -sum(self._keep_priority(card) for card in action.chosen)

        score = 30 * len(action.chosen)

        if "game start" in tips:
            return sum(self._opening_active_priority(card) for card in action.chosen)

        if source_name == "Rare Candy":
            if "stage 2 Pokemon" in tips:
                return score + sum(
                    self._rare_candy_evolution_priority(card) for card in action.chosen
                )
            if "basic Pokemon" in tips:
                return score + sum(self._rare_candy_basic_priority(card) for card in action.chosen)

        if source_name == "Charizard ex":
            return score + sum(self._infernal_reign_priority(card, state) for card in action.chosen)

        if source_name in {"Buddy-Buddy Poffin", "Nest Ball"}:
            return score + sum(SETUP_POKEMON.get(self._name(card), 0) for card in action.chosen)

        if source_name in {"Quick Search", "Pidgeot ex", "Ultra Ball", "Lumineon V", "Arven"}:
            return score + sum(self._search_priority(card, state) for card in action.chosen)

        if source_name == "Prime Catcher" and "your benched Pokemon" in tips:
            return score + sum(self._switch_in_priority(card) for card in action.chosen)

        if (
            source_name in {"Boss's Orders", "Counter Catcher", "Prime Catcher"}
            or "opponent" in tips
        ):
            return score + sum(self._gust_target_priority(card) for card in action.chosen)

        return score + sum(self._search_priority(card, state) for card in action.chosen)

    def _opening_active_priority(self, card: Any) -> float:
        name = self._name(card)
        return {"Cleffa": 300, "Rotom V": 280, "Charmander": 240, "Pidgey": 120}.get(name, 60)

    def _rare_candy_evolution_priority(self, card: Any) -> float:
        return {"Charizard ex": 500, "Pidgeot ex": 430}.get(self._name(card), 100)

    def _rare_candy_basic_priority(self, card: Any) -> float:
        return {"Charmander": 500, "Pidgey": 420}.get(self._name(card), 100)

    def _infernal_reign_priority(self, card: Any, state: State) -> float:
        if "Fire Energy" not in self._name(card):
            return 0
        player = self._player(state, state.turn)
        active_name = self._name(player.active[0]) if player and player.active else ""
        return 120 if active_name == "Charizard ex" else 90

    def _search_priority(self, card: Any, state: State) -> float:
        name = self._name(card)
        player = self._player(state, state.turn)

        if player:
            in_play = [self._name(card) for card in player.active + player.bench]
            hand = [self._name(card) for card in player.hand]
            if name == "Charizard ex" and "Charmander" not in in_play:
                return 20
            if name == "Pidgeot ex" and "Pidgey" not in in_play:
                return 20
            if name == "Rare Candy" and not any(
                card_name in hand for card_name in {"Charizard ex", "Pidgeot ex"}
            ):
                return 35

        return SEARCH_TARGETS.get(name, 10)

    def _gust_target_priority(self, card: Any) -> float:
        hp = getattr(card, "hp", 0)
        prize = getattr(card, "prize", 1)
        name = self._name(card)
        score = 100 * prize + max(0, 250 - hp)
        if name in {"Pidgeot ex", "Charizard ex", "Gholdengo ex", "Lugia VSTAR"}:
            score += 150
        if name in {"Charmander", "Pidgey", "Bidoof"}:
            score += 90
        return score

    def _switch_in_priority(self, card: Any) -> float:
        return {"Charizard ex": 500, "Radiant Charizard": 430, "Pidgeot ex": 260}.get(
            self._name(card), 80
        )

    def _keep_priority(self, card: Any) -> float:
        return DISCARD_KEEP_PRIORITY.get(self._name(card), 30)

    def _has_ready_attacker(self, state: State, player_id: PlayerId) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        for pokemon in player.active + player.bench:
            if (
                self._name(pokemon) in {"Charizard ex", "Radiant Charizard"}
                and len(getattr(pokemon, "energy", [])) >= 2
            ):
                return True
        return False

    def _player(self, state: State, player_id: PlayerId | None):
        if player_id == PlayerId.PLAYER1:
            return state.player1
        if player_id == PlayerId.PLAYER2:
            return state.player2
        return None

    def _opponent(self, state: State, player_id: PlayerId):
        if player_id == PlayerId.PLAYER1:
            return state.player2
        if player_id == PlayerId.PLAYER2:
            return state.player1
        return None

    def _name(self, obj: Any) -> str:
        return getattr(obj, "name", "")
