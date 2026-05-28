"""ExpeL (Experiential Learning) agent for PTCG battles.

Implements the ExpeL framework from Zhao et al. (2024) "ExpeL: LLM Agents Are Experiential Learners":
  - Actor:      ReAct loop (Thought → tool call → Observation)
  - Experience: rolling pool of raw game trajectories with outcomes
  - Extractor:  post-batch LLM call compares wins vs losses → actionable rule set
  - Retriever:  deck-matchup similarity selects k past games as few-shot examples

Differences from Reflexion:
  Reflexion writes one verbal reflection per game (sequential, single-game view).
  ExpeL accumulates a pool of raw trajectories, then distils cross-game insights by
  comparing successes and failures in bulk (post_batch). At inference time it also
  retrieves the k most similar past games as demonstration examples in the system prompt.
"""

from __future__ import annotations
import json_repair

import json
import logging
import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from toon_format import encode

from ptcgbench.agents.base_agent import BaseAgent
from ptcgbench.agents.common.model_client import (
    assistant_message_to_history,
    build_client,
    chat_completion_with_retry,
)
from ptcgbench.agents.common.profile import AgentConfig, AgentProfile, BattleRecord
from ptcgbench.agents.trace import TraceRecorder
from ptcgbench.agents.interfaces.executor import ToolCallExecutor
from ptcgbench.agents.interfaces.observer import StateObserver
from ptcgbench.agents.interfaces.schema import StateObservation
from ptcgbench.agents.tools.tool_dispatcher import ToolDispatcher
from ptcgbench.agents.tools.tool_schemas import (
    get_tool_schemas,
    is_game_action_tool,
    is_general_tool,
    parse_tool_call_arguments,
)
from ptcg.core.action import Action
from ptcg.core.state import State
from ptcg.utils.load_deck import _resolve_deck_path

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    keep_trailing_newline=True,
)

_OBS_EXCLUDE = {
    "my": {
        "active": {
            "__all__": {
                "card_type",
                "stage",
                "pokemon_type",
                "retreat_cost",
                "attacks",
                "abilities",
                "prize",
            }
        },
        "bench": {
            "__all__": {
                "card_type",
                "stage",
                "pokemon_type",
                "retreat_cost",
                "attacks",
                "abilities",
                "prize",
            }
        },
        "discard": True,
    },
    "opponent": {
        "active": {
            "__all__": {
                "card_type",
                "stage",
                "pokemon_type",
                "retreat_cost",
                "attacks",
                "abilities",
                "prize",
            }
        },
        "bench": {
            "__all__": {
                "card_type",
                "stage",
                "pokemon_type",
                "retreat_cost",
                "attacks",
                "abilities",
                "prize",
            }
        },
        "discard": True,
    },
}

# ── Insight extraction prompts ────────────────────────────────────────────────

_EXTRACT_PROMPT = """\
You are a Pokémon TCG strategy coach analysing completed games played by the same agent.

## Winning Games
{wins_text}

## Losing Games
{losses_text}

## Task
Study the contrast between wins and losses. Produce exactly {max_insights} concise, \
actionable rules that the agent should follow in future games.

Rules must:
- Reference specific PTCG mechanics, card types, or timing decisions
- Be prescriptive ("Always...", "Avoid...when...", "Prioritise X over Y")
- Be general enough to apply across matchups

Return ONLY a JSON array of strings — one string per rule. No other text.
["Rule 1...", "Rule 2...", ...]
"""

_UPDATE_PROMPT = """\
You are a Pokémon TCG strategy coach refining an existing rule set given new game evidence.

## Current Rules
{current_rules_text}

## New Evidence

### Winning Games
{wins_text}

### Losing Games
{losses_text}

## Task
Update the rule set to at most {max_insights} rules.
Incorporate lessons from the new evidence: keep what holds, drop what the evidence contradicts,
and add new rules only when clearly supported.

Return ONLY a JSON array of strings — the complete updated rule list. No other text.
["Rule 1...", "Rule 2...", ...]
"""


# ── Experience dataclass ──────────────────────────────────────────────────────


@dataclass
class Experience:
    id: str
    result: str  # "win" | "loss" | "draw"
    my_deck: str
    opponent_deck: str
    turns: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "result": self.result,
            "my_deck": self.my_deck,
            "opponent_deck": self.opponent_deck,
            "turns": self.turns,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Experience":
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            result=d.get("result", "unknown"),
            my_deck=d.get("my_deck", ""),
            opponent_deck=d.get("opponent_deck", ""),
            turns=d.get("turns", []),
        )


def _format_experiences(experiences: list[Experience], max_turns: int = 10) -> str:
    if not experiences:
        return "(none)"
    parts = []
    for i, exp in enumerate(experiences, 1):
        turns = exp.turns[:max_turns]
        trace = "\n".join(
            f"  Turn {t + 1}: {entry.get('thought', '')} → {entry.get('action', '')}"
            for t, entry in enumerate(turns)
        )
        parts.append(
            f"Game {i} [{exp.result.upper()}] ({exp.my_deck} vs {exp.opponent_deck}):\n{trace}"
        )
    return "\n\n".join(parts)


# ── Agent ─────────────────────────────────────────────────────────────────────


class ExpeLAgent(BaseAgent):
    """Agent that learns via experience collection and cross-game insight extraction.

    Components:
    - Actor:       ReAct loop (Thought → tool call → Observation)
    - Experience:  rolling pool of raw game trajectories (wins + losses)
    - Extractor:   batch LLM call in post_batch() compares wins vs losses to distil
                   a set of actionable strategic rules (insights)
    - Retriever:   deck-matchup similarity selects retrieval_k past games as
                   few-shot examples injected into the system prompt each new game
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        max_experience: int = 50,
        max_insights: int = 10,
        retrieval_k: int = 3,
        temperature: float = 0.7,
        max_retries: int = 3,
        max_messages: int = 40,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.max_experience = max_experience
        self.max_insights = max_insights
        self.retrieval_k = retrieval_k
        self.temperature = temperature
        self.max_retries = max_retries
        self.max_messages = max_messages

        self._last_game_history: list[dict[str, str]] = []
        self._current_my_deck: str = ""
        self._current_opponent_deck: str = ""
        self.trace_recorder = TraceRecorder()

        # Agent profile
        self.name = f"expel_{model}"
        self.profile = AgentProfile(name=self.name)
        self.profile.save_config(
            AgentConfig(
                name=self.name,
                model=self.model,
                architecture="expel",
                temperature=self.temperature,
                max_retries=self.max_retries,
            )
        )

        # Battle state
        self._battle_record: BattleRecord | None = None
        self._turn_count: int = 0

        # Persistent memory
        self._pool_path = self.profile.memory_dir / "experience_pool.json"
        self._insights_path = self.profile.memory_dir / "insights.json"
        self._pending_dir = self.profile.memory_dir / "pending_experiences"
        self.experience_pool: list[Experience] = self._load_pool()
        self.insights: list[str] = self._load_insights()

        # LLM client
        self._client = build_client(model)

        # Reusable components
        self.observer = StateObserver()
        self.executor = ToolCallExecutor()
        self.tool_dispatcher = ToolDispatcher(observer=self.observer)
        self._tool_schemas = get_tool_schemas()

        # Conversation history (rebuilt with insights + examples at each game start)
        self._base_system_prompt = _jinja_env.get_template("system/react.md").render()
        self._messages: list[dict[str, Any]] = []
        self._reset_messages()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_pool(self) -> list[Experience]:
        if not self._pool_path.exists():
            return []
        try:
            data = json.loads(self._pool_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [Experience.from_dict(d) for d in data]
        except Exception:
            logger.exception("Failed to load experience pool from %s", self._pool_path)
        return []

    def _save_pool(self) -> None:
        try:
            self._pool_path.write_text(
                json.dumps(
                    [e.to_dict() for e in self.experience_pool],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to save experience pool to %s", self._pool_path)

    def _load_insights(self) -> list[str]:
        if not self._insights_path.exists():
            return []
        try:
            data = json.loads(self._insights_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(r) for r in data]
        except Exception:
            logger.exception("Failed to load insights from %s", self._insights_path)
        return []

    def _save_insights(self) -> None:
        try:
            self._insights_path.write_text(
                json.dumps(self.insights, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to save insights to %s", self._insights_path)

    # ── Insight extraction ────────────────────────────────────────────────────

    def _extract_insights(self, wins: list[Experience], losses: list[Experience]) -> list[str]:
        """Call LLM to distil rules by contrasting win/loss experience samples."""
        wins_text = _format_experiences(wins)
        losses_text = _format_experiences(losses)

        if self.insights:
            current_rules_text = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(self.insights))
            prompt = _UPDATE_PROMPT.format(
                current_rules_text=current_rules_text,
                wins_text=wins_text,
                losses_text=losses_text,
                max_insights=self.max_insights,
            )
        else:
            prompt = _EXTRACT_PROMPT.format(
                wins_text=wins_text,
                losses_text=losses_text,
                max_insights=self.max_insights,
            )

        try:
            response = chat_completion_with_retry(
                self._client,
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_completion_tokens=1024,
            )
            raw = (response.choices[0].message.content or "").strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            parsed = json_repair.loads(raw)
            if isinstance(parsed, list):
                return [str(r) for r in parsed[: self.max_insights]]
        except Exception:
            logger.exception("Insight extraction LLM call failed")
        return self.insights  # keep existing on failure

    # ── Experience retrieval ──────────────────────────────────────────────────

    def _matchup_score(self, exp: Experience, my_deck: str, opponent_deck: str) -> float:
        """Deck-matchup similarity in [0, 1]."""
        match_my = exp.my_deck == my_deck
        match_opp = exp.opponent_deck == opponent_deck
        if match_my and match_opp:
            return 1.0
        if match_my:
            return 0.6
        if match_opp:
            return 0.4
        return 0.0

    def _retrieve_experiences(self, my_deck: str, opponent_deck: str) -> list[Experience]:
        """Return retrieval_k most relevant past experiences for the current matchup.

        Guarantees at least one win is included when possible, so the few-shot
        context always has a positive example to emulate.
        """
        if not self.experience_pool:
            return []
        ranked = sorted(
            self.experience_pool,
            key=lambda e: self._matchup_score(e, my_deck, opponent_deck),
            reverse=True,
        )
        top = ranked[: self.retrieval_k]
        # Ensure at least one winning example if available outside top-k
        if not any(e.result == "win" for e in top):
            for e in ranked[self.retrieval_k :]:
                if e.result == "win":
                    top[-1] = e
                    break
        return top

    # ── System-prompt assembly ────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        parts = [self._base_system_prompt]

        if self.insights:
            rules_text = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(self.insights))
            parts.append(
                "\n\n## Strategic Insights\n\n"
                "These rules were distilled from analysing past games. "
                "Apply them when making decisions this game.\n\n" + rules_text
            )

        examples = self._retrieve_experiences(self._current_my_deck, self._current_opponent_deck)
        if examples:
            ex_blocks = []
            for e in examples:
                trace = "\n".join(
                    f"  T{t + 1}: {entry.get('thought', '')} → {entry.get('action', '')}"
                    for t, entry in enumerate(e.turns[:8])
                )
                ex_blocks.append(f"[{e.result.upper()}] {e.my_deck} vs {e.opponent_deck}\n{trace}")
            parts.append(
                "\n\n## Retrieved Similar Games\n\n"
                "These past games used a similar deck matchup. "
                "Use them as reference — repeat what worked, avoid what failed.\n\n"
                + "\n\n".join(ex_blocks)
            )

        return "".join(parts)

    def _reset_messages(self) -> None:
        self._messages = [{"role": "system", "content": self._build_system_prompt()}]

    # ── Observation helpers ───────────────────────────────────────────────────

    def _build_user_message(self, observation: StateObservation) -> str:
        return encode(
            observation.model_dump(exclude_none=True, exclude_defaults=True, exclude=_OBS_EXCLUDE)
        )

    def _truncate_history(self) -> None:
        while len(self._messages) > self.max_messages:
            if len(self._messages) <= 1:
                break
            self._messages.pop(1)
            while len(self._messages) > 1 and self._messages[1].get("role") == "tool":
                self._messages.pop(1)

    # ── BaseAgent interface ───────────────────────────────────────────────────

    def predict(self, obs: State, info: dict[str, Any]) -> Action:
        """Run one ReAct step with insight- and example-augmented context."""
        available = info.get("raw_available_actions", [])
        if not available:
            raise ValueError("No available actions")
        observation = self.observer.observe(obs, info, available_actions=available)

        # Hidden card selection (e.g. prize cards) — random pick, skip LLM
        prompt = info.get("prompt")
        if prompt and getattr(prompt, "hidden", False):
            return random.choice(available)

        user_msg = self._build_user_message(observation)
        self._messages.append({"role": "user", "content": user_msg})
        self._truncate_history()

        attempt = 0
        while attempt < self.max_retries:
            response = chat_completion_with_retry(
                self._client,
                model=self.model,
                messages=self._messages,
                temperature=self.temperature,
                tools=self._tool_schemas,
                tool_choice="auto",
            )
            message = response.choices[0].message
            thought = message.content or ""

            if not message.tool_calls:
                attempt += 1
                self._messages.append(assistant_message_to_history(message))
                self._messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Please select an action using one of the available tools.\n"
                            f"Attempt {attempt}/{self.max_retries}."
                        ),
                    }
                )
                continue

            self._messages.append(assistant_message_to_history(message))

            action_to_return: Action | None = None
            for tool_call in message.tool_calls:
                tool_name, arguments = parse_tool_call_arguments(tool_call)

                if is_general_tool(tool_name):
                    result_text = self.tool_dispatcher.dispatch(tool_name, arguments, obs)
                    self._messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result_text,
                        }
                    )
                    continue

                if is_game_action_tool(tool_name):
                    result = self.executor.execute(tool_name, arguments, info)

                    if result.level == "FULL":
                        self._messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": f"OK: {result.action.to_nl()}",
                            }
                        )
                        if action_to_return is None:
                            action_to_return = result.action
                            self._last_game_history.append(
                                {"thought": thought, "action": result.action.to_nl()}
                            )
                            self.trace_recorder.record_turn(
                                observation, thought, result.action.to_nl()
                            )
                    else:
                        attempt += 1
                        self._messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": (
                                    f"Action failed: {result.reason}\n"
                                    f"Attempt {attempt}/{self.max_retries}. "
                                    "Try a different action."
                                ),
                            }
                        )

            if action_to_return is not None:
                return action_to_return

        logger.warning("ExpeL agent falling back to random action")
        self._last_game_history.append({"thought": "fallback", "action": "random"})
        self.trace_recorder.record_turn(observation, "fallback", "random")
        return random.choice(available)

    def on_game_end(self, result: str) -> None:
        """Write this game's experience to a pending file.

        Using a unique file per game avoids write conflicts when multiple
        per-game instances run concurrently. post_batch() consolidates these.
        """
        game_trace = self.trace_recorder.finalize(
            result=result,
            my_deck=self._current_my_deck,
            opp_deck=self._current_opponent_deck,
        )
        if self._battle_record is not None:
            game_trace.save(self._battle_record.record_dir / "trace.json")

        exp = Experience(
            id=str(uuid.uuid4()),
            result=result,
            my_deck=self._current_my_deck,
            opponent_deck=self._current_opponent_deck,
            turns=list(self._last_game_history),
        )
        self._pending_dir.mkdir(parents=True, exist_ok=True)
        pending_file = self._pending_dir / f"{exp.id}.json"
        try:
            pending_file.write_text(
                json.dumps(exp.to_dict(), ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to save pending experience to %s", pending_file)
        self._last_game_history.clear()
        self.trace_recorder.reset()

    def reset(self) -> None:
        """Reset per-game state. Experience pool and insights persist."""
        self._last_game_history.clear()
        self.trace_recorder.reset()
        self._reset_messages()

    def notify_game_start(
        self,
        my_deck: str,
        opponent_deck: str,
        opponent_name: str = "",
    ) -> None:
        """Register deck matchup and reset context for the new game."""
        self._turn_count = 0
        self._current_my_deck = my_deck
        self._current_opponent_deck = opponent_deck
        try:
            resolved_my_deck_path: Path | None = _resolve_deck_path(my_deck)
        except FileNotFoundError:
            try:
                resolved_my_deck_path = _resolve_deck_path(
                    Path(str(my_deck)).stem.replace("-", "_")
                )
            except FileNotFoundError:
                resolved_my_deck_path = None
        try:
            resolved_opponent_deck_path: Path | None = _resolve_deck_path(opponent_deck)
        except FileNotFoundError:
            try:
                resolved_opponent_deck_path = _resolve_deck_path(
                    Path(str(opponent_deck)).stem.replace("-", "_")
                )
            except FileNotFoundError:
                resolved_opponent_deck_path = None
        self._battle_record = BattleRecord(
            battles_dir=self.profile.battles_dir,
            my_deck=my_deck,
            opponent_deck=opponent_deck,
            agent_name=self.name,
            opponent_name=opponent_name,
            my_deck_path=resolved_my_deck_path,
            opponent_deck_path=resolved_opponent_deck_path,
        )
        self.reset()

    def post_batch(
        self,
        battle_summary: dict,
        history_path: Path,
    ) -> dict:
        """Consolidate pending experiences and update insights.

        Called once per batch by eval_pipeline on the persistent batch_agent instance,
        after all per-game instances have finished and written their pending files.

        Steps:
        1. Load pending experience files into the pool.
        2. If both wins and losses exist, extract/update insights via LLM.
        3. Persist pool and insights; delete pending files.
        """
        if not self._pending_dir.is_dir():
            return {"experiences_added": 0, "insights_updated": False}

        pending_files = sorted(self._pending_dir.glob("*.json"))
        added = 0
        for f in pending_files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self.experience_pool.append(Experience.from_dict(data))
                added += 1
            except Exception:
                logger.exception("Failed to load pending experience from %s", f)

        if len(self.experience_pool) > self.max_experience:
            self.experience_pool = self.experience_pool[-self.max_experience :]

        insights_updated = False
        if added:
            self._save_pool()
            print(f"  {self.name} pool: +{added} experiences ({len(self.experience_pool)} total)")

            wins = [e for e in self.experience_pool if e.result == "win"]
            losses = [e for e in self.experience_pool if e.result == "loss"]
            if wins and losses:
                sample_wins = random.sample(wins, min(len(wins), 3))
                sample_losses = random.sample(losses, min(len(losses), 3))
                new_insights = self._extract_insights(sample_wins, sample_losses)
                if new_insights:
                    self.insights = new_insights
                    self._save_insights()
                    insights_updated = True
                    print(f"  {self.name} insights: {len(self.insights)} rules updated")

        for f in pending_files:
            try:
                f.unlink()
            except Exception:
                pass

        return {"experiences_added": added, "insights_updated": insights_updated}

    def close(self, result: str = "", my_prizes: int = 0, opponent_prizes: int = 0) -> None:
        if self._battle_record is not None:
            self._battle_record.write_summary(
                result=result or "unknown",
                turn_count=self._turn_count,
                my_prizes_remaining=my_prizes,
                opponent_prizes_remaining=opponent_prizes,
            )

    def post_game(self, result: str = "", my_prizes: int = 0, opponent_prizes: int = 0) -> None:
        self.close(result, my_prizes, opponent_prizes)
        self.on_game_end(result)
