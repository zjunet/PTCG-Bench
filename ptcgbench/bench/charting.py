"""Chart generator for evaluation pipeline metrics.

Produces a single PNG with 3 vertically stacked subplots sharing the x-axis
(game number): Glicko-2 rating +/-RD, rolling win rate, and steps per game.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend — must be set before pyplot import
import matplotlib.pyplot as plt

from ptcgbench.bench.metrics import MetricsCollector


def plot_eval_metrics(
    metrics: MetricsCollector,
    output_path: Path,
    window: int = 10,
    agent_ids: list[str] | None = None,
    deck: str = "",
) -> Path:
    """Generate a 3-subplot evaluation chart and save to *output_path*.

    Subplots (top to bottom):
    1. Glicko-2 rating for each agent with +/-RD shaded band
    2. Rolling win rate over *window* games for the first agent
    3. Steps per game with a moving-average line

    Returns the path the chart was saved to.
    """
    records = metrics.records
    if not records:
        return output_path

    game_ids = [r.game_id for r in records]
    steps = [r.steps for r in records]

    # Determine which agents to plot ratings for (deduplicated, order-preserving).
    if agent_ids is None:
        # Derive unique agent IDs from the records themselves.
        seen: list[str] = []
        for r in records:
            for aid in (r.p1_id, r.p2_id):
                if aid not in seen:
                    seen.append(aid)
        agent_ids = seen
    else:
        # Deduplicate while preserving order.
        seen = []
        for aid in agent_ids:
            if aid not in seen:
                seen.append(aid)
        agent_ids = seen

    # Collect rating and true RD (phi) series from whichever side (p1 or p2) they appear.
    _COLORS = ["#2563eb", "#dc2626", "#16a34a", "#f59e0b", "#8b5cf6", "#ec4899"]
    rating_series: dict[str, list[float]] = {aid: [] for aid in agent_ids}
    rd_series: dict[str, list[float]] = {aid: [] for aid in agent_ids}

    for r in records:
        for aid in agent_ids:
            # Prefer p1 if agent appears on both sides (self-play), else whichever side.
            if r.p1_id == aid:
                rating_series[aid].append(r.p1_rating_after)
                rd = r.p1_phi_after
            elif r.p2_id == aid:
                rating_series[aid].append(r.p2_rating_after)
                rd = r.p2_phi_after
            else:
                # Agent not in this game — carry forward last known state or default.
                last = rating_series[aid][-1] if rating_series[aid] else 1500.0
                rating_series[aid].append(last)
                rd = rd_series[aid][-1] if rd_series[aid] else 350.0
            rd_series[aid].append(max(rd, 20.0))

    # Rolling win rate per agent.
    win_rate_per_agent: dict[str, list[tuple[int, float]]] = {
        aid: metrics.rolling_win_rate(window=window, agent_id=aid) for aid in agent_ids
    }

    # Moving average for steps
    ma_window = min(window, len(steps))
    steps_ma: list[float] = []
    for i in range(len(steps)):
        start = max(0, i - ma_window + 1)
        chunk = steps[start : i + 1]
        steps_ma.append(sum(chunk) / len(chunk))

    # --- Plot ---
    title_prefix = " vs ".join(agent_ids)
    if deck:
        title_prefix += f" ({deck})"

    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(12, 10), sharex=True, gridspec_kw={"hspace": 0.25}
    )
    fig.suptitle(f"{title_prefix} — Evaluation Metrics", fontsize=14, fontweight="bold")

    # Subplot 1: Glicko rating + confidence band per agent
    for idx, aid in enumerate(agent_ids):
        color = _COLORS[idx % len(_COLORS)]
        ratings = rating_series[aid]
        rds = rd_series[aid]
        ax1.plot(game_ids, ratings, linewidth=2, color=color, label=aid)
        ax1.fill_between(
            game_ids,
            [m - rd for m, rd in zip(ratings, rds)],
            [m + rd for m, rd in zip(ratings, rds)],
            alpha=0.12,
            color=color,
        )
    ax1.set_ylabel("Glicko-2 Rating")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_title("Rating")

    # Subplot 2: Rolling win rate (one line per agent)
    for idx, aid in enumerate(agent_ids):
        color = _COLORS[idx % len(_COLORS)]
        wr_data = win_rate_per_agent[aid]
        wr_ids = [gid for gid, _ in wr_data]
        wr_vals = [rate for _, rate in wr_data]
        ax2.plot(
            wr_ids,
            wr_vals,
            linewidth=2,
            color=color,
            label=f"{aid} (window={window})",
        )
    ax2.axhline(y=0.5, color="gray", linestyle="--", alpha=0.5, label="50%")
    ax2.set_ylim(-0.05, 1.05)
    ax2.set_ylabel("Win Rate")
    ax2.legend(loc="upper left", fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_title("Rolling Win Rate")

    # Subplot 3: Steps per game
    ax3.scatter(game_ids, steps, s=12, alpha=0.6, color="#dc2626", label="Steps")
    ax3.plot(game_ids, steps_ma, linewidth=2, color="#dc2626", alpha=0.8, label=f"MA({ma_window})")
    ax3.set_xlabel("Game Number")
    ax3.set_ylabel("Steps")
    ax3.legend(loc="upper left", fontsize=9)
    ax3.grid(True, alpha=0.3)
    ax3.set_title("Steps per Game")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path
