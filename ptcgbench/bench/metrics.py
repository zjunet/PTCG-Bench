"""Metrics collection for the evaluation pipeline."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class GameMetrics:
    """Per-game metrics record."""

    game_id: int
    batch_id: int
    p1_id: str
    p2_id: str
    winner_id: str  # agent ID of winner, or "draw"
    steps: int
    timestamp: str
    p1_rating_before: float
    p1_rating_after: float
    p2_rating_before: float
    p2_rating_after: float
    p1_phi_before: float = 350.0
    p1_phi_after: float = 350.0
    p2_phi_before: float = 350.0
    p2_phi_after: float = 350.0


class MetricsCollector:
    """Collects per-game metrics and computes derived statistics."""

    def __init__(self) -> None:
        self._records: list[GameMetrics] = []

    def record_game(self, metrics: GameMetrics) -> None:
        self._records.append(metrics)

    @property
    def records(self) -> list[GameMetrics]:
        return self._records

    def rolling_win_rate(
        self, window: int = 10, agent_id: str | None = None
    ) -> list[tuple[int, float]]:
        """Calculate rolling win rate over the last *window* games.

        When *agent_id* is given, counts games where that agent won
        (i.e. ``r.winner_id == agent_id``).  When ``None``, falls back to
        counting any non-draw as a win for backward-compatibility tests.

        Returns a list of ``(game_id, win_rate)`` tuples, one per recorded game.
        The rate at position *i* covers games ``[max(0, i - window + 1), i]``.
        """
        results: list[tuple[int, float]] = []
        for i, record in enumerate(self._records):
            start = max(0, i - window + 1)
            window_records = self._records[start : i + 1]
            if agent_id is not None:
                wins = sum(1 for r in window_records if r.winner_id == agent_id)
            else:
                wins = sum(1 for r in window_records if r.winner_id != "draw")
            rate = wins / len(window_records)
            results.append((record.game_id, rate))
        return results

    def summary(self, agent_ids: list[str] | None = None) -> dict:
        """Return aggregate statistics over all recorded games.

        When *agent_ids* is provided, per-agent win counts and win rates are
        included as ``{aid}_wins`` / ``{aid}_win_rate`` keys.
        """
        if not self._records:
            return {"total": 0}
        draws = sum(1 for r in self._records if r.winner_id == "draw")
        avg_steps = sum(r.steps for r in self._records) / len(self._records)
        result: dict = {
            "total": len(self._records),
            "draws": draws,
            "avg_steps": avg_steps,
        }
        if agent_ids:
            for aid in agent_ids:
                wins = sum(1 for r in self._records if r.winner_id == aid)
                played = sum(1 for r in self._records if r.p1_id == aid or r.p2_id == aid)
                result[f"{aid}_wins"] = wins
                result[f"{aid}_win_rate"] = wins / played if played else 0.0
        return result

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(r) for r in self._records]
        path.write_text(json.dumps(data, indent=2))

    def load(self, path: Path) -> None:
        data = json.loads(path.read_text())
        self._records = [GameMetrics(**r) for r in data]
