"""Evaluation pipeline: run arbitrary agent pairs in batches with metrics tracking.

Usage:
    # Two agents (classic)
    uv run python -m ptcgbench.bench.eval_pipeline --agents random random --n-games 20

    # Heuristic baseline against random
    uv run python -m ptcgbench.bench.eval_pipeline --agents charizard_heuristic random --n-games 20

    # Multiple agents (round-robin tournament)
    uv run python -m ptcgbench.bench.eval_pipeline --agents random skillevolving:deepseek-chat react:deepseek-chat --n-games 30

    # Show global leaderboard without running games
    uv run python -m ptcgbench.bench.eval_pipeline --show

    # Update global ratings file after run
    uv run python -m ptcgbench.bench.eval_pipeline --agents random random --n-games 20 --global-ratings
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import weave

from ptcgbench.agents.base_agent import BaseAgent
from ptcgbench.agents.charizard_heuristic_agent import CharizardHeuristicAgent
from ptcgbench.agents.common.profile import AgentProfile
from ptcgbench.agents.random_agent import RandomAgent
from ptcgbench.bench.charting import plot_eval_metrics
from ptcgbench.bench.leaderboard import GameResult, Leaderboard
from ptcgbench.bench.live_progress import (
    BatchLiveProgress,
    get_active_live_progress,
    live_progress_session,
)
from ptcgbench.bench.metrics import GameMetrics, MetricsCollector
from ptcg.core.enums import PlayerId
from ptcg.core.envs import PokemonTCG

os.environ["WEAVE_ENABLE_WAL"] = "true"

os.environ["WEAVE_HTTP_TIMEOUT"] = "120"
os.environ["WEAVE_RETRY_MAX_ATTEMPTS"] = "8"
os.environ["WEAVE_RETRY_MAX_INTERVAL"] = "300"

weave_eval_client = weave.init(f"eval_pipeline_{datetime.now().strftime('%Y-%m-%d')}")


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def _make_agent(agent_id: str) -> BaseAgent:
    """Instantiate an agent from an ID like 'random' or 'skillevolving:deepseek-chat'."""
    if agent_id == "random":
        return RandomAgent()
    if agent_id == "charizard_heuristic":
        return CharizardHeuristicAgent()
    if ":" not in agent_id:
        raise ValueError(
            f"Unknown agent_id: {agent_id!r}. Use 'random', 'charizard_heuristic', "
            "or '<type>:<model>' "
            "(e.g. 'skillevolving:deepseek-chat', 'react:deepseek-chat')."
        )
    agent_type, model = agent_id.split(":", 1)
    if agent_type == "skillevolving":
        from ptcgbench.agents.skill_evolving_agent import SkillEvolvingAgent

        return SkillEvolvingAgent(model=model)
    if agent_type == "react":
        from ptcgbench.agents.react_agent import ReActAgent

        return ReActAgent(model=model)
    if agent_type == "reflexion":
        from ptcgbench.agents.reflexion_agent import ReflexionAgent

        return ReflexionAgent(model=model)
    if agent_type == "prompt_evolving":
        from ptcgbench.agents.prompt_evolving_agent import PromptEvolvingAgent

        return PromptEvolvingAgent(model=model)
    if agent_type == "expel":
        from ptcgbench.agents.expel_agent import ExpeLAgent

        return ExpeLAgent(model=model)
    if agent_type == "ltm":
        from ptcgbench.agents.ltm_agent import LTMAgent

        return LTMAgent(model=model)
    if agent_type == "gepa":
        from ptcgbench.agents.gepa_agent import GEPAAgent

        return GEPAAgent(model=model)
    raise ValueError(
        f"Unknown agent type: {agent_type!r}. Use 'random', 'charizard_heuristic', "
        "'skillevolving', 'react', 'reflexion', 'prompt_evolving', 'expel', 'ltm', or 'gepa'."
    )


_LLM_TYPES = {"skillevolving", "react", "reflexion", "prompt_evolving", "expel", "ltm", "gepa"}


def _is_llm_agent(agent_id: str) -> bool:
    if ":" not in agent_id:
        return False
    return agent_id.split(":", 1)[0] in _LLM_TYPES


def _finalize_agent_game(
    agent: BaseAgent,
    *,
    result: str,
    my_prizes: int,
    opponent_prizes: int,
    replay_file: str | Path | None,
) -> None:
    agent.post_game(result=result, my_prizes=my_prizes, opponent_prizes=opponent_prizes)

    if replay_file is None:
        return

    battle_record = getattr(agent, "_battle_record", None)
    if battle_record is not None:
        battle_record.save_replay(replay_file)


def _agent_battles_dir(agent: BaseAgent) -> Path | None:
    profile = getattr(agent, "profile", None)
    return getattr(profile, "battles_dir", None)


def _agent_skills_dir(agent: BaseAgent) -> Path | None:
    profile = getattr(agent, "profile", None)
    return getattr(profile, "skills_dir", None)


# ---------------------------------------------------------------------------
# PipelineGameRunner (weave.Model)
# ---------------------------------------------------------------------------


class PipelineGameRunner(weave.Model):
    """weave Model that runs a single PTCG game with rich lifecycle hooks."""

    deck: str
    max_steps: int = 500
    progress_update_every: int = 5

    def _run_game(self, p1_id: str, p2_id: str, seed: int, game_id: int) -> dict:
        """Run a single game, returning outcome metadata."""
        p1_agent = _make_agent(p1_id)
        p2_agent = _make_agent(p2_id)

        env = PokemonTCG(seed=seed, deck1=self.deck, deck2=self.deck, record_game=True)
        p1_agent.reset()
        p2_agent.reset()
        obs, _reward, done, info = env.reset()

        deck_name = AgentProfile.deck_name_from_path(self.deck)
        p1_name = getattr(p1_agent, "name", p1_id)
        p2_name = getattr(p2_agent, "name", p2_id)

        p1_agent.notify_game_start(deck_name, deck_name, opponent_name=p2_name)
        p2_agent.notify_game_start(deck_name, deck_name, opponent_name=p1_name)

        progress = get_active_live_progress()
        if progress is not None:
            progress.start_game(seed, info.get("turn"))

        steps = 0
        try:
            while not done and steps < self.max_steps:
                actions = info.get("raw_available_actions", [])
                if not actions:
                    break
                turn: PlayerId = info.get("turn")
                action = (
                    p1_agent.predict(obs, info)
                    if turn == PlayerId.PLAYER1
                    else p2_agent.predict(obs, info)
                )
                obs, _reward, done, info = env.step(action)
                steps += 1
                if progress is not None and (
                    steps == 1
                    or done
                    or steps >= self.max_steps
                    or steps % self.progress_update_every == 0
                ):
                    progress.update_game(seed, steps, info.get("turn"))
        except Exception:
            if progress is not None:
                progress.fail_game(seed, steps)
            raise
        finally:
            winner = info.get("winner") or getattr(env, "winner", None)
            state = obs if hasattr(obs, "player1") else env.gamestate
            p1_prizes = len(state.player1.prize) if hasattr(state, "player1") else 0
            p2_prizes = len(state.player2.prize) if hasattr(state, "player2") else 0

            p1_result = "unknown"
            if winner == PlayerId.PLAYER1:
                p1_result = "win"
            elif winner == PlayerId.PLAYER2:
                p1_result = "loss"
            elif done:
                p1_result = "draw"

            p2_result = (
                "win" if p1_result == "loss" else ("loss" if p1_result == "win" else p1_result)
            )
            replay_file = env.recorder.file_path if env.recorder is not None else None
            _finalize_agent_game(
                p1_agent,
                result=p1_result,
                my_prizes=p1_prizes,
                opponent_prizes=p2_prizes,
                replay_file=replay_file,
            )
            _finalize_agent_game(
                p2_agent,
                result=p2_result,
                my_prizes=p2_prizes,
                opponent_prizes=p1_prizes,
                replay_file=replay_file,
            )

        # Determine winner_id
        if not done:
            winner_id = "draw"
        elif winner == PlayerId.PLAYER1:
            winner_id = p1_id
        elif winner == PlayerId.PLAYER2:
            winner_id = p2_id
        else:
            winner_id = "draw"

        if progress is not None:
            progress.finish_game(seed, winner_id, steps)

        return {
            "game_id": int(game_id),
            "winner_id": str(winner_id),
            "steps": int(steps),
            "p1_id": str(p1_id),
            "p2_id": str(p2_id),
            "seed": int(seed),
        }

    @weave.op()
    def predict(self, p1_id: str, p2_id: str, seed: int, game_id: int) -> dict:
        return self._run_game(p1_id, p2_id, seed, game_id)


# ---------------------------------------------------------------------------
# Thread-safe scorer
# ---------------------------------------------------------------------------

# Thread-safe scorer: module-level function + list, same pattern as scorer callback.
_batch_game_results: list[dict] = []
_batch_lock = threading.Lock()


def _clear_batch_results() -> None:
    with _batch_lock:
        _batch_game_results.clear()


@weave.op()
def game_outcome(output: dict) -> dict:
    """Score a single game and record the raw result for metrics collection."""
    with _batch_lock:
        _batch_game_results.append(output)
    winner_id = output["winner_id"]
    is_draw = winner_id == "draw"
    return {"winner": winner_id, "is_draw": is_draw}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_deck_path(deck_name: str) -> str:
    """Resolve a deck name (e.g. 'charizard_ex') to its full file path."""
    import ptcg.core.envs as _envs_mod

    decks_dir = Path(_envs_mod.__file__).parent.parent / "decks"
    candidate = decks_dir / f"{deck_name}.txt"
    return str(candidate) if candidate.exists() else deck_name


def snapshot_skills(skills_dir: Path, snapshot_dir: Path) -> None:
    """Copy the current skills directory into a snapshot directory."""
    if not skills_dir.is_dir():
        return
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for item in skills_dir.iterdir():
        dest = snapshot_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)


def _list_battle_dirs(battles_dir: Path) -> set[str]:
    """Return the set of battle directory names currently present."""
    if not battles_dir.is_dir():
        return set()
    return {entry.name for entry in battles_dir.iterdir() if entry.is_dir()}


def _stage_batch_battles(source_dirs: list[Path], staging_dir: Path) -> Path | None:
    """Expose only this batch's battle dirs through a temporary directory."""
    if not source_dirs:
        return None

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    for source_dir in source_dirs:
        dest = staging_dir / source_dir.name
        shutil.copytree(source_dir, dest)

    return staging_dir


def print_summary(
    metrics: MetricsCollector, leaderboard: Leaderboard, agent_ids: list[str]
) -> None:
    """Print a summary table of the evaluation run."""
    s = metrics.summary(agent_ids=agent_ids)
    print()
    print("=" * 60)
    print(f"{'EVALUATION SUMMARY':^60}")
    print("=" * 60)
    print(f"  Total games:    {s['total']}")
    for aid in agent_ids:
        wins = s.get(f"{aid}_wins", 0)
        rate = s.get(f"{aid}_win_rate", 0.0)
        print(f"  {aid} wins:     {wins}")
        print(f"  {aid} win rate: {rate:.1%}")
    print(f"  Draws:          {s['draws']}")
    print(f"  Avg steps/game: {s['avg_steps']:.1f}")
    print()
    print(leaderboard.display())


def _save_checkpoint(run_dir: Path, batch_idx: int, n_games_done: int, config: dict) -> None:
    """Save a checkpoint file after each completed batch."""
    ckpt = {
        "last_completed_batch": batch_idx,
        "n_games_completed": n_games_done,
        "config": config,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "checkpoint.json").write_text(json.dumps(ckpt, indent=2))


def _load_checkpoint(run_dir: Path) -> dict | None:
    """Load a checkpoint file, returning None if not found."""
    ckpt_path = run_dir / "checkpoint.json"
    if not ckpt_path.exists():
        return None
    return json.loads(ckpt_path.read_text())


def _build_batch_specs(
    pairs: list[tuple[str, str]],
    n_games: int,
    seed_offset: int,
    symmetric: bool,
    game_id_offset: int,
) -> list[dict]:
    """Build game specs for one batch across all matchup pairs.

    *n_games* total games are distributed evenly across pairs (remainder
    allocated one-per-pair).  When *symmetric* is True, each pair's games
    are split evenly between the two P1/P2 orderings for positional fairness.
    Seeds increment monotonically across all specs.
    """
    if not pairs:
        return []

    n_pairs = len(pairs)
    base = n_games // n_pairs
    remainder = n_games % n_pairs

    specs: list[dict] = []
    for idx, (a1, a2) in enumerate(pairs):
        pair_games = base + (1 if idx < remainder else 0)

        if symmetric and a1 != a2:
            half = pair_games // 2
            extra = pair_games - half * 2
            orderings = [(a1, a2)] * half + [(a2, a1)] * half + [(a1, a2)] * extra
        else:
            orderings = [(a1, a2)] * pair_games

        for p1, p2 in orderings:
            specs.append({"p1_id": p1, "p2_id": p2, "seed": seed_offset, "game_id": game_id_offset})
            seed_offset += 1
            game_id_offset += 1

    return specs


def _extract_batch_results(
    game_results: list[dict], agent_ids: list[str]
) -> tuple[list[GameResult], list[tuple[str, str]]]:
    """Convert raw game outputs into leaderboard-format results."""
    win_loss: list[GameResult] = []
    draws: list[tuple[str, str]] = []
    for r in game_results:
        winner_id, p1_id, p2_id = r["winner_id"], r["p1_id"], r["p2_id"]
        if winner_id == "draw":
            draws.append((p1_id, p2_id))
        else:
            loser_id = p2_id if winner_id == p1_id else p1_id
            win_loss.append((winner_id, loser_id))
    return win_loss, draws


def _update_global_ratings(run_lb: Leaderboard, agent_ids: list[str]) -> None:
    """Merge per-run leaderboard results into the global ratings file."""
    global_lb = Leaderboard(
        ratings_file=Path("bench_data/ratings.json"),
        history_file=Path("bench_data/rating_history.json"),
    )
    for aid in agent_ids:
        run_r = run_lb._ratings[aid]
        g = global_lb.get_or_create(aid)
        g.mu = run_r.mu
        g.phi = run_r.phi
        g.sigma = run_r.sigma
        g.wins += run_r.wins
        g.losses += run_r.losses
        g.draws += run_r.draws
    global_lb.save()
    global_lb.save_history()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run agent evaluation pipeline with metrics tracking."
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=["skillevolving:deepseek-chat", "random"],
        metavar="AGENT_ID",
        help="Evolving agent IDs (2+ for round-robin, 1+ when --anchors is set).",
    )
    parser.add_argument(
        "--anchors",
        nargs="*",
        default=[],
        metavar="AGENT_ID",
        help=(
            "Fixed baseline agents. Each evolving agent plays every anchor; "
            "anchors never play each other and never evolve."
        ),
    )
    parser.add_argument("--deck", default="charizard_ex", help="Deck name (same for both players)")
    parser.add_argument("--n-games", type=int, default=20, help="Total number of games")
    parser.add_argument("--batch-size", type=int, default=5, help="Games per batch")
    parser.add_argument(
        "--max-steps", type=int, default=500, help="Max steps per game (draw threshold)"
    )
    parser.add_argument("--window", type=int, default=10, help="Rolling window for win rate chart")
    parser.add_argument("--seed", type=int, default=0, help="Base random seed")
    parser.add_argument(
        "--symmetric",
        action="store_true",
        default=True,
        help="Split games evenly across P1/P2 sides (default: True)",
    )
    parser.add_argument(
        "--no-symmetric",
        dest="symmetric",
        action="store_false",
        help="Disable symmetric side assignment",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        default=None,
        metavar="RUN_DIR",
        help="Resume a previous run from its run directory",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display global leaderboard without running games",
    )
    parser.add_argument(
        "--global-ratings",
        action="store_true",
        help="Update bench_data/ratings.json after the run",
    )
    parser.add_argument(
        "--inherit-ratings",
        action="store_true",
        help="Seed initial Glicko-2 ratings (mu/phi/sigma) from bench_data/ratings.json",
    )
    parser.add_argument(
        "--live-progress",
        action="store_true",
        help="Show a live table of active games while a batch is running",
    )
    parser.add_argument(
        "--progress-update-every",
        type=int,
        default=5,
        help="Publish live progress every N steps per game",
    )
    parser.add_argument(
        "--progress-refresh-ms",
        type=int,
        default=200,
        help="Refresh interval for the live progress table in milliseconds",
    )
    args = parser.parse_args()

    # --- --show early exit ---
    if args.show:
        lb = Leaderboard(ratings_file=Path("bench_data/ratings.json"))
        print(lb.display())
        return

    anchor_ids: list[str] = args.anchors or []
    if anchor_ids:
        if len(args.agents) < 1 or len(anchor_ids) < 1:
            parser.error("--anchors mode requires at least 1 --agents and 1 --anchors entry.")
    elif len(args.agents) < 2:
        parser.error("At least 2 agent IDs are required (got {}).".format(len(args.agents)))

    # --- Setup ---
    resuming = args.resume is not None
    if resuming:
        run_dir = args.resume
        if not (run_dir / "checkpoint.json").exists():
            print(f"Error: no checkpoint.json found in {run_dir}", file=sys.stderr)
            sys.exit(1)
        ckpt = _load_checkpoint(run_dir)
        assert ckpt is not None
        config = ckpt["config"]
        args.agents = config["agents"]
        anchor_ids = config.get("anchor_ids", [])
        args.deck = config["deck"]
        args.n_games = config["n_games"]
        args.batch_size = config["batch_size"]
        args.max_steps = config["max_steps"]
        args.seed = config["seed"]
        last_completed_batch = ckpt["last_completed_batch"]
        print(f"Resuming from {run_dir} (batch {last_completed_batch + 1} done)")
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        agent_label = "_vs_".join(a.replace(":", "_").replace("/", "_") for a in args.agents)
        run_dir = Path("bench_data/runs") / f"{timestamp}_{agent_label}_{args.deck}"
        run_dir.mkdir(parents=True, exist_ok=True)
        last_completed_batch = -1

    deck_path = resolve_deck_path(args.deck)
    agent_ids: list[str] = args.agents  # evolving agents only

    # All participants (evolving + anchors, deduped, order preserved).
    seen: set[str] = set()
    all_agent_ids: list[str] = []
    for aid in agent_ids + anchor_ids:
        if aid not in seen:
            seen.add(aid)
            all_agent_ids.append(aid)

    # Compute matchup pairs (prefer checkpoint, recompute for old checkpoints).
    if resuming and "pairs" in config:
        pairs = [(p[0], p[1]) for p in config["pairs"]]
    elif anchor_ids:
        # Anchored mode: each evolving agent vs each anchor; anchors never face each other.
        pairs = [(a, anc) for a in agent_ids for anc in anchor_ids]
    else:
        pairs = [
            (agent_ids[i], agent_ids[j])
            for i in range(len(agent_ids))
            for j in range(i + 1, len(agent_ids))
        ]

    # Save config (include pairs for checkpoint compatibility).
    if not resuming:
        config = {
            "agents": args.agents,
            "anchor_ids": anchor_ids,
            "deck": args.deck,
            "n_games": args.n_games,
            "batch_size": args.batch_size,
            "max_steps": args.max_steps,
            "seed": args.seed,
            "pairs": [[a, b] for a, b in pairs],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        (run_dir / "config.json").write_text(json.dumps(config, indent=2))

    leaderboard = Leaderboard(
        ratings_file=run_dir / "ratings.json",
        history_file=run_dir / "rating_history.json",
    )
    for aid in all_agent_ids:
        leaderboard.get_or_create(aid)

    if args.inherit_ratings:
        global_ratings_file = Path("bench_data/ratings.json")
        if global_ratings_file.exists():
            global_lb = Leaderboard(ratings_file=global_ratings_file)
            anchor_set = set(anchor_ids)
            for aid in all_agent_ids:
                if aid in global_lb._ratings:
                    g = global_lb._ratings[aid]
                    r = leaderboard.get_or_create(aid)
                    r.mu, r.phi, r.sigma = g.mu, g.phi, g.sigma
                    print(f"  Inherited rating for {aid}: mu={g.mu:.0f} ±{g.phi:.0f}")
                elif _is_llm_agent(aid):
                    # Fall back to any global rating with the same backbone model (anchors preferred).
                    backbone = aid.split(":", 1)[1]
                    candidates = [
                        (rid, g)
                        for rid, g in global_lb._ratings.items()
                        if ":" in rid and rid.split(":", 1)[1] == backbone and rid != aid
                    ]
                    candidates.sort(key=lambda x: 0 if x[0] in anchor_set else 1)
                    if candidates:
                        source_id, g = candidates[0]
                        r = leaderboard.get_or_create(aid)
                        r.mu, r.phi, r.sigma = g.mu, g.phi, g.sigma
                        print(
                            f"  Inherited rating for {aid} from {source_id}"
                            f" (same backbone {backbone!r}): mu={g.mu:.0f} ±{g.phi:.0f}"
                        )
        else:
            print("  --inherit-ratings: bench_data/ratings.json not found, using defaults.")

    metrics = MetricsCollector()
    if resuming and (run_dir / "metrics.json").exists():
        metrics.load(run_dir / "metrics.json")

    # Batch-level post-processing: only evolving LLM agents (anchors are fixed).
    llm_agents = [aid for aid in agent_ids if _is_llm_agent(aid)]
    batch_agents = {aid: _make_agent(aid) for aid in llm_agents}

    n_batches = (args.n_games + args.batch_size - 1) // args.batch_size
    game_id = len(metrics.records)

    print(f"\nStarting evaluation: {args.n_games} games ({n_batches} batches of {args.batch_size})")
    print(f"  Agents:  {' vs '.join(agent_ids)}")
    if anchor_ids:
        print(f"  Anchors: {', '.join(anchor_ids)}")
    print(f"  Deck:   {args.deck}")
    print(f"  Run directory: {run_dir}\n")

    # Weave game runner.
    runner = PipelineGameRunner(
        deck=deck_path,
        max_steps=args.max_steps,
        progress_update_every=max(1, args.progress_update_every),
    )

    live_progress_enabled = bool(args.live_progress and sys.stdout.isatty())
    if args.live_progress and not live_progress_enabled:
        print("Live progress disabled: stdout is not a TTY.")

    # --- Batch loop ---
    for batch_idx in range(n_batches):
        if batch_idx <= last_completed_batch:
            batch_start = batch_idx * args.batch_size
            batch_end = min(batch_start + args.batch_size, args.n_games)
            game_id = batch_end
            continue

        batch_start = batch_idx * args.batch_size
        batch_end = min(batch_start + args.batch_size, args.n_games)
        batch_size = batch_end - batch_start

        print(f"--- Batch {batch_idx + 1}/{n_batches} ({batch_size} games) ---")

        # Snapshot Glicko state before the batch.
        ratings_before: dict[str, float] = {
            aid: leaderboard._ratings[aid].mu for aid in all_agent_ids
        }
        phi_before: dict[str, float] = {aid: leaderboard._ratings[aid].phi for aid in all_agent_ids}
        batch_battle_baselines = {
            aid: _list_battle_dirs(battles_dir)
            for aid, agent in batch_agents.items()
            if (battles_dir := _agent_battles_dir(agent)) is not None
        }

        # Build game specs and run via weave.Evaluation (parallel within batch).
        game_specs = _build_batch_specs(
            pairs,
            batch_size,
            args.seed + batch_start,
            args.symmetric,
            game_id,
        )

        _clear_batch_results()
        evaluation = weave.Evaluation(
            name=f"batch_{batch_idx}",
            dataset=game_specs,
            scorers=[game_outcome],
        )
        batch_progress: BatchLiveProgress | None = None
        if live_progress_enabled:
            batch_progress = BatchLiveProgress(
                batch_idx=batch_idx,
                n_batches=n_batches,
                batch_size=batch_size,
                total_games=args.n_games,
                completed_before_batch=game_id,
                deck=args.deck,
            )
            for spec in game_specs:
                batch_progress.register_game(
                    game_id=spec["game_id"],
                    p1_id=spec["p1_id"],
                    p2_id=spec["p2_id"],
                    seed=spec["seed"],
                    max_steps=args.max_steps,
                )

        with live_progress_session(batch_progress, args.progress_refresh_ms) as live:
            asyncio.run(evaluation.evaluate(runner))
            if live is not None:
                live.update(batch_progress, refresh=True)

        batch_game_results = list(_batch_game_results)
        batch_game_results.sort(key=lambda result: result["game_id"])

        # Extract leaderboard results and update ratings.
        win_loss, draws = _extract_batch_results(batch_game_results, agent_ids)
        if win_loss:
            leaderboard.record_period(win_loss)
        if draws:
            leaderboard.record_period_draws(draws)
        leaderboard.save()
        leaderboard.save_history()

        # Backfill metrics records for each game in this batch.
        ratings_after: dict[str, float] = {
            aid: leaderboard._ratings[aid].mu for aid in all_agent_ids
        }
        phi_after: dict[str, float] = {aid: leaderboard._ratings[aid].phi for aid in all_agent_ids}

        for result in batch_game_results:
            result_game_id = result["game_id"]
            p1_id, p2_id = result["p1_id"], result["p2_id"]
            p1_rating_before = ratings_before.get(p1_id, 1500.0)
            p2_rating_before = ratings_before.get(p2_id, 1500.0)
            p1_rating_after = ratings_after.get(p1_id, 1500.0)
            p2_rating_after = ratings_after.get(p2_id, 1500.0)
            p1_phi_before = phi_before.get(p1_id, 350.0)
            p2_phi_before = phi_before.get(p2_id, 350.0)
            p1_phi_after = phi_after.get(p1_id, 350.0)
            p2_phi_after = phi_after.get(p2_id, 350.0)

            metrics.record_game(
                GameMetrics(
                    game_id=result_game_id,
                    batch_id=batch_idx,
                    p1_id=p1_id,
                    p2_id=p2_id,
                    winner_id=result["winner_id"],
                    steps=result["steps"],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    p1_rating_before=p1_rating_before,
                    p1_rating_after=p1_rating_after,
                    p2_rating_before=p2_rating_before,
                    p2_rating_after=p2_rating_after,
                    p1_phi_before=p1_phi_before,
                    p1_phi_after=p1_phi_after,
                    p2_phi_before=p2_phi_before,
                    p2_phi_after=p2_phi_after,
                )
            )

            winner_id = result["winner_id"]
            steps = result["steps"]
            if winner_id == "draw":
                print(f"  Game {result_game_id + 1}: Draw after {steps} steps")
            else:
                print(f"  Game {result_game_id + 1}: {winner_id} wins in {steps} steps")

        game_id += batch_size

        # Persist metrics after each batch.
        metrics.save(run_dir / "metrics.json")

        # Batch-level post-processing for persistent agents.
        for aid, agent in batch_agents.items():
            battles_dir = _agent_battles_dir(agent)
            if battles_dir is None:
                continue

            current_dirs = _list_battle_dirs(battles_dir)
            new_dir_names = sorted(current_dirs - batch_battle_baselines.get(aid, set()))
            batch_history = _stage_batch_battles(
                [battles_dir / name for name in new_dir_names],
                run_dir / "reflection_batches" / aid / f"batch_{batch_idx:03d}",
            )
            if batch_history is None:
                print(f"  {aid} skipped batch post-processing: no new battle records in this batch")
                continue

            battle_summary = {
                "my_deck": args.deck,
                "opponent_deck": args.deck,
                "result": "batch",
                "turn_count": sum(r.steps for r in metrics.records[batch_start:batch_end]),
            }
            agent.post_batch(battle_summary=battle_summary, history_path=batch_history)

            skills_dir = _agent_skills_dir(agent)
            if skills_dir is not None:
                skills_snap_dir = run_dir / "skills_snapshots" / aid / f"batch_{batch_idx:03d}"
                snapshot_skills(skills_dir, skills_snap_dir)

        # Save checkpoint for resume support.
        _save_checkpoint(run_dir, batch_idx, game_id, config)

        print()

    # --- Final output ---
    print_summary(metrics, leaderboard, all_agent_ids)

    if args.global_ratings:
        _update_global_ratings(leaderboard, all_agent_ids)
        print(f"  Global ratings updated: bench_data/ratings.json")

    chart_path = plot_eval_metrics(
        metrics,
        run_dir / "chart.png",
        window=args.window,
        agent_ids=agent_ids,
        deck=args.deck,
    )
    print(f"  Chart saved to: {chart_path}")
    print(f"\nArtifacts saved to: {run_dir}")
    weave_eval_client.flush()


if __name__ == "__main__":
    main()
