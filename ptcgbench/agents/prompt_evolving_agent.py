"""PromptEvolving agent: experience-driven strategy prompt updates.

After each game, the agent makes one LLM call to directly revise the
strategy section of its system prompt based on the game trace and
failure patterns (turns where the opponent scored a prize).

Contrast with other baselines:
- Reflexion / ExpeL:  accumulate a knowledge base or insight list that is
  injected alongside the base prompt — the base prompt stays fixed.
- GEPA:               search-based prompt optimisation via multiple eval games
  per batch to score candidate strategies.
- PromptEvolving:     the strategy *text* itself is rewritten once per game,
  no extra eval games, no knowledge-base indirection.  Updates are direct,
  cheap, and compound across games through disk persistence.
"""

from __future__ import annotations

import logging
from typing import Any

from ptcgbench.agents.common.model_client import chat_completion_with_retry
from ptcgbench.agents.common.profile import AgentConfig, AgentProfile
from ptcgbench.agents.react_agent import ReActAgent, _render_system_prompt
from ptcg.core.action import Action
from ptcg.core.state import State

logger = logging.getLogger(__name__)

_UPDATE_PROMPT = """\
You are a Pokémon TCG strategy coach. Revise the strategy guide below based on the last game.

## Current Strategy
{current_strategy}

## Last Game
Result: {result} | Turns played: {total_turns}
My deck: {my_deck} | Opponent deck: {opp_deck}

## Game Trace (key decision steps, up to 30)
{trace_text}

## Failure Patterns (turns where opponent took a prize card)
{failure_text}

## Task
Rewrite the strategy guide to address the failure patterns above and reinforce what worked.
Rules:
- Be prescriptive: "Always...", "When X, do Y", "Avoid Z if..."
- Reference specific game mechanics (prize race, KO priority, energy attachment timing)
- Keep it under {max_words} words total
- On a win: strengthen what drove the win; note any close calls to avoid next time
- On a loss: root-cause the failures shown above; suggest concrete fixes

Output ONLY the revised strategy text — no JSON, no section headers, no preamble.
"""


class PromptEvolvingAgent(ReActAgent):
    """ReActAgent with experience-driven per-game strategy prompt updates.

    Each game instance loads the latest strategy from disk, plays using the
    ReAct loop, then rewrites the strategy based on the outcome and failure
    patterns in a single LLM call.  The revised strategy is persisted so the
    next game instance starts from the improved version.
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        update_temperature: float = 0.3,
        max_strategy_words: int = 400,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, **kwargs)
        self.name = f"prompt_evolving_{model}"
        self.profile = AgentProfile(name=self.name)
        self.profile.save_config(
            AgentConfig(
                name=self.name,
                model=model,
                architecture="prompt_evolving",
                temperature=kwargs.get("temperature", 0.7),
                max_retries=kwargs.get("max_retries", 3),
            )
        )

        self._update_temperature = update_temperature
        self._max_strategy_words = max_strategy_words
        self._strategy_path = self.profile.agent_dir / "strategy.md"
        self._current_strategy = self._load_strategy()

        # Extended trace: each entry mirrors self.trace but adds prize counts
        # and active Pokémon names so failure patterns can be identified.
        self._ext_trace: list[dict[str, Any]] = []
        self._current_my_deck = ""
        self._current_opp_deck = ""

        self._rebuild_system_prompt()

    # ------------------------------------------------------------------
    # Strategy persistence
    # ------------------------------------------------------------------

    def _load_strategy(self) -> str:
        if self._strategy_path.exists():
            return self._strategy_path.read_text(encoding="utf-8").strip()
        return ""

    def _rebuild_system_prompt(self) -> None:
        base = _render_system_prompt()
        full = (
            base + "\n\n## Strategy\n\n" + self._current_strategy
            if self._current_strategy
            else base
        )
        self._system_prompt = full
        if self._messages and self._messages[0]["role"] == "system":
            self._messages[0]["content"] = full

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def notify_game_start(
        self,
        my_deck: str,
        opponent_deck: str,
        opponent_name: str = "",
    ) -> None:
        self._current_my_deck = my_deck
        self._current_opp_deck = opponent_deck
        self._ext_trace.clear()
        # super() calls reset() which uses self._system_prompt; ours is already up-to-date
        super().notify_game_start(my_deck, opponent_deck, opponent_name)

    def predict(self, obs: State, info: dict[str, Any]) -> Action:
        available = info.get("raw_available_actions", [])
        if not available:
            raise ValueError("No available actions")

        # Observe once here to capture prize state; super().predict() re-observes
        # but state is identical so the overhead is just a cheap dict transform.
        observation = self.observer.observe(obs, info, available_actions=available)
        my_prizes = observation.my.prize_count
        opp_prizes = observation.opponent.prize_count
        my_active = observation.my.active[0].name if observation.my.active else ""
        opp_active = observation.opponent.active[0].name if observation.opponent.active else ""

        prev_len = len(self.trace)
        action = super().predict(obs, info)

        # Append one entry per successful action (same cadence as self.trace)
        if len(self.trace) > prev_len:
            self._ext_trace.append(
                {
                    **self.trace[-1],
                    "my_prizes": my_prizes,
                    "opp_prizes": opp_prizes,
                    "my_active": my_active,
                    "opp_active": opp_active,
                }
            )
        return action

    def post_game(self, result: str = "", my_prizes: int = 0, opponent_prizes: int = 0) -> None:
        super().post_game(result, my_prizes, opponent_prizes)
        self._evolve_strategy(result)

    # ------------------------------------------------------------------
    # Strategy evolution
    # ------------------------------------------------------------------

    def _evolve_strategy(self, result: str) -> None:
        if not self._ext_trace:
            return

        # Identify turns where opponent scored (prize count dropped)
        failure_indices: list[int] = []
        prev_opp: int | None = None
        for i, t in enumerate(self._ext_trace):
            if prev_opp is not None and t["opp_prizes"] < prev_opp:
                failure_indices.append(i)
            prev_opp = t["opp_prizes"]

        # Abbreviated trace (up to 30 steps)
        trace_lines: list[str] = []
        for i, t in enumerate(self._ext_trace[:30]):
            trace_lines.append(
                f"T{i + 1} [me:{t['my_prizes']} opp:{t['opp_prizes']}]"
                f" ({t['my_active']} vs {t['opp_active']}) → {t['action']}"
            )

        # Context windows around each failure (2 turns of lead-up + the failure turn)
        failure_lines: list[str] = []
        for idx in failure_indices[:5]:
            opp_before = self._ext_trace[idx - 1]["opp_prizes"] if idx > 0 else "?"
            failure_lines.append(
                f"--- Opponent scored: prizes {opp_before} → {self._ext_trace[idx]['opp_prizes']} ---"
            )
            context_start = max(0, idx - 2)
            for c in self._ext_trace[context_start : idx + 1]:
                failure_lines.append(
                    f"  [me:{c['my_prizes']} opp:{c['opp_prizes']}]"
                    f" thought: {c['thought'][:120]}"
                    f" | action: {c['action']}"
                )

        prompt = _UPDATE_PROMPT.format(
            current_strategy=self._current_strategy
            or "(none yet — write an initial strategy from scratch)",
            result=result,
            total_turns=len(self._ext_trace),
            my_deck=self._current_my_deck,
            opp_deck=self._current_opp_deck,
            trace_text="\n".join(trace_lines) if trace_lines else "(no trace recorded)",
            failure_text="\n".join(failure_lines)
            if failure_lines
            else "(opponent did not score — maintain aggressive pressure)",
            max_words=self._max_strategy_words,
        )

        try:
            response = chat_completion_with_retry(
                self._client,
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self._update_temperature,
                max_completion_tokens=700,
            )
            new_strategy = (response.choices[0].message.content or "").strip()
            if new_strategy:
                self._current_strategy = new_strategy
                self.profile.ensure_dirs()
                self._strategy_path.write_text(new_strategy, encoding="utf-8")
                self._rebuild_system_prompt()
                print(f"  {self.name}: strategy updated ({len(new_strategy)} chars)")
        except Exception:
            logger.exception("Strategy update LLM call failed; keeping previous strategy")
        finally:
            self._ext_trace.clear()
