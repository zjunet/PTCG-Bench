from __future__ import annotations

from pydantic import BaseModel, model_validator


class AttackInfo(BaseModel):
    name: str
    damage: int
    cost: list[str]
    text: str = ""


class AbilityInfo(BaseModel):
    name: str
    ability_type: str
    text: str = ""


class PokemonObservation(BaseModel):
    id: str
    name: str
    hp: int
    damage_counters: int = 0
    card_type: str
    stage: str
    pokemon_type: str
    retreat_cost: list[str]
    energy: list[str] = []
    tools: list[str] = []
    attacks: list[AttackInfo]
    abilities: list[AbilityInfo]
    prize: int


class CardObservation(BaseModel):
    id: str
    name: str


class PlayerObservation(BaseModel):
    active: list[PokemonObservation]
    bench: list[PokemonObservation] = []
    hand: list[CardObservation] = []
    hand_count: int
    deck_count: int
    prize_count: int
    discard: list[CardObservation] = []
    discard_count: int
    energy_played: bool = False
    supporter_played: bool = False
    retreated: bool = False

    @model_validator(mode="after")
    def validate_hand_count(self) -> "PlayerObservation":
        if self.hand:
            if self.hand_count != len(self.hand):
                raise ValueError(
                    f"hand_count ({self.hand_count}) must equal len(hand) ({len(self.hand)}) "
                    "when hand is non-empty"
                )
        return self


class StateObservation(BaseModel):
    turn: str
    turn_number: int
    timestep: int
    my: PlayerObservation
    opponent: PlayerObservation
    stadium: str | None
    choosing_card: bool = False
    choosing_tips: str = ""
    opponent_last_turn_actions: list[str] = []
    available_actions: list[str] = []
