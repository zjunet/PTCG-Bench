from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


class PokemonSnapshot(BaseModel):
    name: str
    current_hp: int
    max_hp: int
    energy: list[str] = []


class TurnRecord(BaseModel):
    turn_number: int
    timestep: int
    my_prizes: int
    opp_prizes: int
    my_active: PokemonSnapshot | None = None
    opp_active: PokemonSnapshot | None = None
    available_actions: list[str] = []
    thought: str = ""
    action: str = ""
    my_scored: bool = False
    opp_scored: bool = False


class GameSummary(BaseModel):
    result: str
    total_turns: int
    my_deck: str = ""
    opp_deck: str = ""
    my_prize_progression: list[int] = []
    opp_prize_progression: list[int] = []
    inflection_indices: list[int] = []


class GameTrace(BaseModel):
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    turns: list[TurnRecord] = []
    summary: GameSummary | None = None

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> GameTrace:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class CriticalWindow(BaseModel):
    inflection_timestep: int
    opp_prizes_before: int
    opp_prizes_after: int
    turns: list[TurnRecord]


class ExtractedTrace(BaseModel):
    """Compact trace for a reflector LLM: game arc + decision windows around each inflection."""

    summary: GameSummary
    windows: list[CriticalWindow]
