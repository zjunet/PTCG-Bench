"""Agent rating registry and leaderboard with persistent JSON storage."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ptcgbench.bench.glicko2 import Glicko2System, GlickoPlayer

GameResult = tuple[str, Optional[str]]

_DEFAULT_RATINGS_FILE = Path("bench_data/ratings.json")
_DEFAULT_HISTORY_FILE = Path("bench_data/rating_history.json")


@dataclass
class RatingSnapshot:
    mu: float
    phi: float
    sigma: float


@dataclass
class PeriodRecord:
    period: int
    timestamp: str
    agents: dict[str, RatingSnapshot]


@dataclass
class AgentRating:
    agent_id: str
    mu: float = 1500.0
    phi: float = 350.0
    sigma: float = 0.06
    wins: int = 0
    losses: int = 0
    draws: int = 0

    def to_glicko_player(self) -> GlickoPlayer:
        return GlickoPlayer(mu=self.mu, phi=self.phi, sigma=self.sigma)

    def update_from_glicko(self, player: GlickoPlayer) -> None:
        self.mu = player.mu
        self.phi = player.phi
        self.sigma = player.sigma


class Leaderboard:
    def __init__(
        self,
        ratings_file: Path = _DEFAULT_RATINGS_FILE,
        history_file: Path = _DEFAULT_HISTORY_FILE,
    ):
        self.ratings_file = Path(ratings_file)
        self.history_file = Path(history_file)
        self._ratings: dict[str, AgentRating] = {}
        self._history: list[PeriodRecord] = []
        self._current_period: int = 0
        if self.ratings_file.exists():
            self.load()
        if self.history_file.exists():
            self.load_history()

    def get_or_create(self, agent_id: str) -> AgentRating:
        if agent_id not in self._ratings:
            self._ratings[agent_id] = AgentRating(agent_id=agent_id)
        return self._ratings[agent_id]

    def record_period(self, period_results: list[GameResult]) -> None:
        """Apply one Glicko-2 rating period using all results in the list.

        Args:
            period_results: List of (winner_id, loser_id) tuples.
                            loser_id=None means the game was a draw between
                            winner_id and a second player — but for draws we
                            encode them as (player_a, player_b) with a special
                            sentinel.  See eval_pipeline.py for the convention used.
        """
        # Ensure all mentioned players exist
        all_ids: set[str] = set()
        for a, b in period_results:
            all_ids.add(a)
            if b is not None:
                all_ids.add(b)
        for aid in all_ids:
            self.get_or_create(aid)

        # Build per-player result lists: {agent_id: [(opponent_glicko, score)]}
        match_map: dict[str, list[tuple[GlickoPlayer, float]]] = {aid: [] for aid in self._ratings}

        for winner_id, loser_id in period_results:
            if loser_id is None:
                # Draw encoded as (player_a, None) — shouldn't happen with our
                # convention; skip gracefully.
                continue

            winner_glicko = self._ratings[winner_id].to_glicko_player()
            loser_glicko = self._ratings[loser_id].to_glicko_player()

            # Distinguish draws from wins using a sentinel: winner_id == loser_id
            if winner_id == loser_id:
                # Draw: both get 0.5
                # (This sentinel is never produced by eval_pipeline — draws use
                #  a separate tuple convention described below.)
                match_map[winner_id].append((loser_glicko, 0.5))
                match_map[loser_id].append((winner_glicko, 0.5))
            else:
                match_map[winner_id].append((loser_glicko, 1.0))
                match_map[loser_id].append((winner_glicko, 0.0))

        # Update W/L/D tallies BEFORE changing ratings (we need old ratings for Glicko)
        for winner_id, loser_id in period_results:
            if loser_id is None:
                continue
            if winner_id == loser_id:
                self._ratings[winner_id].draws += 1  # self-play treated as draw
            else:
                self._ratings[winner_id].wins += 1
                self._ratings[loser_id].losses += 1

        # Apply Glicko-2 updates — snapshot current ratings first so updates
        # don't feed into each other within the same period.
        old_glicko: dict[str, GlickoPlayer] = {
            aid: r.to_glicko_player() for aid, r in self._ratings.items()
        }
        for aid, rating in self._ratings.items():
            new_player = Glicko2System.update(old_glicko[aid], match_map.get(aid, []))
            rating.update_from_glicko(new_player)

        self._record_snapshot()

    def record_period_draws(self, draw_pairs: list[tuple[str, str]]) -> None:
        """Record draw results separately (helper used by eval_pipeline)."""
        for a, b in draw_pairs:
            self.get_or_create(a)
            self.get_or_create(b)

        old_glicko: dict[str, GlickoPlayer] = {
            aid: r.to_glicko_player() for aid, r in self._ratings.items()
        }
        match_map: dict[str, list[tuple[GlickoPlayer, float]]] = {aid: [] for aid in self._ratings}
        for a, b in draw_pairs:
            match_map[a].append((old_glicko[b], 0.5))
            match_map[b].append((old_glicko[a], 0.5))
            self._ratings[a].draws += 1
            self._ratings[b].draws += 1

        for aid, rating in self._ratings.items():
            new_player = Glicko2System.update(old_glicko[aid], match_map.get(aid, []))
            rating.update_from_glicko(new_player)

        self._record_snapshot()

    def save(self) -> None:
        self.ratings_file.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for aid, r in self._ratings.items():
            d = asdict(r)
            del d["agent_id"]  # redundant — key is the agent_id
            data[aid] = d
        self.ratings_file.write_text(json.dumps(data, indent=2))

    def load(self) -> None:
        data = json.loads(self.ratings_file.read_text())
        for aid, fields in data.items():
            self._ratings[aid] = AgentRating(agent_id=aid, **fields)

    def load_history(self) -> None:
        data = json.loads(self.history_file.read_text())
        self._history = []
        for record in data.get("periods", []):
            agents = {aid: RatingSnapshot(**snap) for aid, snap in record["agents"].items()}
            self._history.append(
                PeriodRecord(period=record["period"], timestamp=record["timestamp"], agents=agents)
            )
        if self._history:
            self._current_period = max(r.period for r in self._history)

    def _record_snapshot(self) -> None:
        self._current_period += 1
        timestamp = datetime.now().isoformat()
        agents = {
            aid: RatingSnapshot(mu=r.mu, phi=r.phi, sigma=r.sigma)
            for aid, r in self._ratings.items()
        }
        self._history.append(
            PeriodRecord(period=self._current_period, timestamp=timestamp, agents=agents)
        )

    def save_history(self) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "periods": [
                {
                    "period": r.period,
                    "timestamp": r.timestamp,
                    "agents": {aid: asdict(snap) for aid, snap in r.agents.items()},
                }
                for r in self._history
            ]
        }
        self.history_file.write_text(json.dumps(data, indent=2))

    def get_history(self) -> list[PeriodRecord]:
        return self._history

    def display(self) -> str:
        """Return a plain-text ranked leaderboard table."""
        if not self._ratings:
            return "(no ratings yet)"

        sorted_agents = sorted(self._ratings.values(), key=lambda r: r.mu, reverse=True)

        col_agent = max(len("Agent"), max(len(r.agent_id) for r in sorted_agents))
        header = f"{'Agent':<{col_agent}}  {'Rating':>6}  {'±RD':>5}  {'W':>5}  {'L':>5}  {'D':>5}"
        sep = "-" * len(header)
        lines = [sep, header, sep]
        for r in sorted_agents:
            lines.append(
                f"{r.agent_id:<{col_agent}}  {r.mu:>6.0f}  {r.phi:>5.0f}  "
                f"{r.wins:>5}  {r.losses:>5}  {r.draws:>5}"
            )
        lines.append(sep)
        return "\n".join(lines)
