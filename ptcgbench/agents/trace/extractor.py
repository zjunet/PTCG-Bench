from __future__ import annotations

from ptcgbench.agents.trace.schema import CriticalWindow, ExtractedTrace, GameTrace, TurnRecord


class CriticalWindowExtractor:
    """Extract decision windows around prize-loss inflection points from a GameTrace.

    Each window contains `window_size` turns leading up to (and including) the turn where
    the opponent scored a prize. These windows give a reflector LLM focused context to
    diagnose strategic mistakes without consuming the full game history.
    """

    def __init__(self, window_size: int = 3) -> None:
        self.window_size = window_size

    def extract(self, trace: GameTrace) -> ExtractedTrace:
        assert trace.summary is not None, "GameTrace must be finalized before extraction"

        windows: list[CriticalWindow] = []

        for idx in trace.summary.inflection_indices:
            start = max(0, idx - self.window_size + 1)
            window_turns: list[TurnRecord] = list(trace.turns[start : idx + 1])

            opp_prizes_before = trace.turns[start].opp_prizes
            opp_prizes_after = trace.turns[idx].opp_prizes

            windows.append(
                CriticalWindow(
                    inflection_timestep=trace.turns[idx].timestep,
                    opp_prizes_before=opp_prizes_before,
                    opp_prizes_after=opp_prizes_after,
                    turns=window_turns,
                )
            )

        return ExtractedTrace(summary=trace.summary, windows=windows)
