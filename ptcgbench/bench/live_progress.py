from __future__ import annotations

import threading
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.live import Live
from rich.table import Table
from rich.text import Text

from ptcg.core.enums import PlayerId


class BatchLiveProgress:
    """Thread-safe batch progress state rendered as a live terminal table."""

    _STATUS_STYLES = {
        "pending": "black on grey70",
        "running": "bold black on cyan",
        "done": "bold black on green3",
        "error": "bold white on red3",
    }

    _TURN_STYLES = {
        "PLAYER1": "bold bright_cyan",
        "PLAYER2": "bold bright_yellow",
        "-": "dim",
    }

    def __init__(
        self,
        *,
        batch_idx: int,
        n_batches: int,
        batch_size: int,
        total_games: int,
        completed_before_batch: int,
        deck: str,
    ) -> None:
        self.batch_idx = batch_idx
        self.n_batches = n_batches
        self.batch_size = batch_size
        self.total_games = total_games
        self.completed_before_batch = completed_before_batch
        self.deck = deck
        self._entries: dict[int, dict[str, Any]] = {}
        self._recent: deque[dict[str, Any]] = deque(maxlen=5)
        self._lock = threading.Lock()

    def register_game(
        self, game_id: int, p1_id: str, p2_id: str, seed: int, max_steps: int
    ) -> None:
        with self._lock:
            self._entries[seed] = {
                "game_id": game_id,
                "p1_id": p1_id,
                "p2_id": p2_id,
                "seed": seed,
                "steps": 0,
                "max_steps": max_steps,
                "turn": "-",
                "status": "pending",
                "winner_id": None,
            }

    def start_game(self, seed: int, turn: PlayerId | None) -> None:
        with self._lock:
            entry = self._entries.get(seed)
            if entry is None:
                return
            entry["status"] = "running"
            entry["turn"] = turn.name if turn is not None else "-"

    def update_game(self, seed: int, steps: int, turn: PlayerId | None) -> None:
        with self._lock:
            entry = self._entries.get(seed)
            if entry is None:
                return
            entry["status"] = "running"
            entry["steps"] = steps
            entry["turn"] = turn.name if turn is not None else "-"

    def finish_game(self, seed: int, winner_id: str, steps: int) -> None:
        with self._lock:
            entry = self._entries.get(seed)
            if entry is None or entry["status"] in {"done", "error"}:
                return
            entry["steps"] = steps
            entry["winner_id"] = winner_id
            entry["status"] = "done"
            self._recent.append(
                {
                    "game_id": entry["game_id"],
                    "winner_id": winner_id,
                    "steps": steps,
                    "p1_id": entry["p1_id"],
                    "p2_id": entry["p2_id"],
                }
            )

    def fail_game(self, seed: int, steps: int) -> None:
        with self._lock:
            entry = self._entries.get(seed)
            if entry is None or entry["status"] in {"done", "error"}:
                return
            entry["steps"] = steps
            entry["status"] = "error"
            self._recent.append(
                {
                    "game_id": entry["game_id"],
                    "winner_id": "error",
                    "steps": steps,
                    "p1_id": entry["p1_id"],
                    "p2_id": entry["p2_id"],
                }
            )

    def _progress_text(self, steps: int, max_steps: int) -> Text:
        if max_steps <= 0:
            return Text("-", style="dim")
        progress_pct = max(0.0, min(steps / max_steps, 1.0))
        filled = min(10, int(progress_pct * 10))
        bar = "█" * filled + "·" * (10 - filled)
        if progress_pct < 0.33:
            style = "bold green3"
        elif progress_pct < 0.66:
            style = "bold yellow3"
        elif progress_pct < 0.9:
            style = "bold dark_orange"
        else:
            style = "bold red3"

        text = Text()
        text.append(bar, style=style)
        text.append(f" {progress_pct * 100:5.1f}%", style="bold white")
        return text

    def _turn_text(self, turn: str) -> Text:
        return Text(turn, style=self._TURN_STYLES.get(turn, "bold"))

    def _status_text(self, status: str) -> Text:
        return Text(f" {status.upper()} ", style=self._STATUS_STYLES.get(status, "bold"))

    def render(self) -> Group:
        with self._lock:
            entries = [dict(entry) for entry in self._entries.values()]
            recent = list(self._recent)

        batch_done = sum(1 for entry in entries if entry["status"] in {"done", "error"})
        total_done = self.completed_before_batch + batch_done
        active_entries = sorted(
            (entry for entry in entries if entry["status"] == "running"),
            key=lambda entry: entry["game_id"],
        )

        title = Text()
        title.append("Evaluation", style="bold bright_cyan")
        title.append(": ", style="bold")
        title.append(f"{self.total_games}", style="bold white")
        title.append(" games total", style="white")
        title.append(" | ", style="dim")
        title.append("Batch ", style="white")
        title.append(f"{self.batch_idx + 1}/{self.n_batches}", style="bold bright_magenta")
        title.append(" | ", style="dim")
        title.append("Deck: ", style="white")
        title.append(self.deck, style="bold green3")

        summary = Text()
        summary.append("Batch progress: ", style="white")
        summary.append(f"{batch_done}/{self.batch_size}", style="bold bright_magenta")
        summary.append(" done", style="white")
        summary.append(" | ", style="dim")
        summary.append("active: ", style="white")
        summary.append(str(len(active_entries)), style="bold bright_cyan")
        summary.append(" | ", style="dim")
        summary.append("total finished: ", style="white")
        summary.append(f"{total_done}/{self.total_games}", style="bold green3")

        table = Table(
            header_style="bold white",
            border_style="bright_black",
            row_styles=["none", "dim"],
            expand=True,
        )
        table.add_column("game", justify="right", style="bold bright_white", no_wrap=True)
        table.add_column("matchup", overflow="fold", style="white")
        table.add_column("steps", justify="right", style="bright_white", no_wrap=True)
        table.add_column("progress", justify="right", no_wrap=True)
        table.add_column("turn", justify="center", no_wrap=True)
        table.add_column("status", justify="center", no_wrap=True)

        if active_entries:
            for entry in active_entries:
                table.add_row(
                    str(entry["game_id"] + 1),
                    f"{entry['p1_id']} vs {entry['p2_id']}",
                    f"{entry['steps']} / {entry['max_steps']}",
                    self._progress_text(entry["steps"], entry["max_steps"]),
                    self._turn_text(entry["turn"]),
                    self._status_text(entry["status"]),
                )
        else:
            table.add_row("-", Text("No active games", style="dim italic"), "-", "-", "-", "-")

        recent_lines: list[Text] = [Text("Recent completions:", style="bold bright_cyan")]
        if recent:
            for item in reversed(recent):
                if item["winner_id"] == "draw":
                    line = Text()
                    line.append(f"- Game {item['game_id'] + 1}: ", style="white")
                    line.append("draw", style="bold yellow3")
                    line.append(f" after {item['steps']} steps", style="white")
                elif item["winner_id"] == "error":
                    line = Text()
                    line.append(f"- Game {item['game_id'] + 1}: ", style="white")
                    line.append(f"{item['p1_id']} vs {item['p2_id']}", style="white")
                    line.append(" errored", style="bold red3")
                    line.append(f" after {item['steps']} steps", style="white")
                else:
                    line = Text()
                    line.append(f"- Game {item['game_id'] + 1}: ", style="white")
                    line.append(item["winner_id"], style="bold green3")
                    line.append(f" wins in {item['steps']} steps", style="white")
                recent_lines.append(line)
        else:
            recent_lines.append(Text("- No completed games yet", style="dim"))

        return Group(title, summary, table, *recent_lines)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.render()


_active_progress: BatchLiveProgress | None = None
_active_progress_lock = threading.Lock()


def get_active_live_progress() -> BatchLiveProgress | None:
    with _active_progress_lock:
        return _active_progress


def _set_active_live_progress(progress: BatchLiveProgress | None) -> None:
    global _active_progress
    with _active_progress_lock:
        _active_progress = progress


@contextmanager
def live_progress_session(
    progress: BatchLiveProgress | None, refresh_ms: int
) -> Iterator[Live | None]:
    _set_active_live_progress(progress)
    try:
        if progress is None:
            yield None
            return

        with Live(
            progress,
            refresh_per_second=max(1, int(1000 / max(1, refresh_ms))),
            screen=True,
            transient=True,
            redirect_stdout=False,
            redirect_stderr=False,
        ) as live:
            yield live
    finally:
        _set_active_live_progress(None)
