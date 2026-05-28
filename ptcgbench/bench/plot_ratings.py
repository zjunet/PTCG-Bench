"""Plot agent rating history using matplotlib.

Usage:
    uv run python -m ptcgbench.bench.plot_ratings
    uv run python -m ptcgbench.bench.plot_ratings --agents random llm:deepseek-chat
    uv run python -m ptcgbench.bench.plot_ratings --output ratings_plot.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt

_DEFAULT_HISTORY_FILE = Path("bench_data/rating_history.json")


def load_history(history_file: Path) -> dict:
    if not history_file.exists():
        raise FileNotFoundError(f"History file not found: {history_file}")
    return json.loads(history_file.read_text())


def plot_ratings(
    history_data: dict,
    agents: Optional[list[str]] = None,
    output: Optional[str] = None,
    show: bool = True,
) -> None:
    periods = history_data.get("periods", [])
    if not periods:
        print("No history data to plot.")
        return

    all_agents: set[str] = set()
    for record in periods:
        all_agents.update(record["agents"].keys())

    if agents:
        all_agents = all_agents.intersection(agents)
        if not all_agents:
            print(f"No matching agents found. Available: {all_agents}")
            return

    agent_data: dict[str, dict[str, list]] = {
        aid: {"periods": [], "mu": [], "phi": []} for aid in all_agents
    }

    for record in periods:
        period = record["period"]
        for aid in all_agents:
            if aid in record["agents"]:
                snap = record["agents"][aid]
                agent_data[aid]["periods"].append(period)
                agent_data[aid]["mu"].append(snap["mu"])
                agent_data[aid]["phi"].append(snap["phi"])

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = plt.cm.tab10.colors
    for idx, (aid, data) in enumerate(sorted(agent_data.items())):
        if not data["periods"]:
            continue
        color = colors[idx % len(colors)]
        periods_list = data["periods"]
        mu_list = data["mu"]
        phi_list = data["phi"]

        ax.plot(periods_list, mu_list, label=aid, color=color, linewidth=2)

        upper = [m + p for m, p in zip(mu_list, phi_list)]
        lower = [m - p for m, p in zip(mu_list, phi_list)]
        ax.fill_between(periods_list, lower, upper, color=color, alpha=0.2)

    ax.set_xlabel("Period", fontsize=12)
    ax.set_ylabel("Rating (μ)", fontsize=12)
    ax.set_title("Agent Glicko-2 Rating History", fontsize=14)
    ax.legend(loc="best", fontsize=10)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if output:
        plt.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {output}")

    if show:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot agent rating history.")
    parser.add_argument(
        "--history-file",
        type=Path,
        default=_DEFAULT_HISTORY_FILE,
        help="Path to rating history JSON (default: bench_data/rating_history.json)",
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        metavar="AGENT_ID",
        help="Filter to specific agents (default: all)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Save plot to file (e.g., ratings.png)",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Don't display the plot (useful with --output)",
    )
    args = parser.parse_args()

    history_data = load_history(args.history_file)
    plot_ratings(
        history_data,
        agents=args.agents,
        output=args.output,
        show=not args.no_show,
    )


if __name__ == "__main__":
    main()
