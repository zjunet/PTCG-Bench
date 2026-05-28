"""Reflexion agent for PTCG battles.

Extends the ReAct pattern with post-game self-evaluation. After each game,
the agent generates a verbal reflection, stores it in memory, and retrieves
past reflections to improve future decisions.

Reference: Shinn et al. (2023) "Reflexion: Language Agents with Verbal Reinforcement Learning"
  - Actor:    ReAct loop (Thought → Action → Observation)
  - Evaluator: post-game LLM call that identifies key mistakes / good moves
  - Memory:   rolling window of verbal reflections injected into the system prompt
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from toon_format import encode

from ptcgbench.agents.base_agent import BaseAgent
from ptcgbench.agents.common.model_client import assistant_message_to_history, build_client
from ptcgbench.agents.common.profile import AgentConfig, AgentProfile, BattleRecord
from ptcgbench.agents.trace import TraceRecorder
from ptcgbench.agents.trace.schema import GameTrace
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

_EVAL_PROMPT = """\
You are a Pokémon TCG self-reflection coach reviewing a completed game.

Game result: {result}

## Turn-by-Turn Trace
{history_text}

## Your Task

Write a 2–4 sentence reflection that:
1. Identifies the most important mistake (if you lost) or the decisive move (if you won).
2. Ends with one concrete heuristic to apply in future games.

Be specific — reference the actual cards and turns involved.
Respond in plain text only. No JSON, no bullet points, no markdown.
"""

# Fields stripped from the state observation sent to the LLM (reduces context noise)
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


class ReflexionAgent(BaseAgent):
    """Agent that learns from past games via self-reflection.

    Components:
    - Actor:     ReAct loop (Thought → tool call → Observation)
    - Evaluator: post-game LLM call that produces a verbal self-reflection
    - Memory:    rolling window of reflections injected into the system prompt
                 at the start of each new game
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        max_reflections: int = 30,
        temperature: float = 0.7,
        max_retries: int = 3,
        max_messages: int = 40,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.max_reflections = max_reflections
        self.temperature = temperature
        self.max_retries = max_retries
        self.max_messages = max_messages
        self._last_game_history: list[dict[str, Any]] = []
        self.trace_recorder = TraceRecorder()

        # Agent profile
        self.name = f"reflexion_{model}"
        self.profile = AgentProfile(name=self.name)
        self.profile.save_config(
            AgentConfig(
                name=self.name,
                model=self.model,
                architecture="reflexion",
                temperature=self.temperature,
                max_retries=self.max_retries,
            )
        )

        # Battle state
        self._battle_record: BattleRecord | None = None
        self._turn_count: int = 0

        # Persistent reflection memory
        self._reflections_path = self.profile.memory_dir / "reflections.json"
        self._pending_dir = self.profile.memory_dir / "pending_reflections"
        self.reflections = self._load_reflections()

        # LLM client
        self._client = build_client(model)

        # Reusable components
        self.observer = StateObserver()
        self.executor = ToolCallExecutor()
        self.tool_dispatcher = ToolDispatcher(observer=self.observer)
        self._tool_schemas = get_tool_schemas()

        # Conversation history (rebuilt with reflections at each game start)
        self._base_system_prompt = _jinja_env.get_template("system/react.md").render()
        self._messages: list[dict[str, Any]] = []
        self._reset_messages()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_reflections(self) -> list[dict[str, str]]:
        """Load reflections from disk, returning an empty list if none exist."""
        if not self._reflections_path.exists():
            return []
        try:
            data = json.loads(self._reflections_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            logger.exception("Failed to load reflections from %s", self._reflections_path)
        return []

    def _save_reflections(self) -> None:
        """Write the current reflection list to disk."""
        try:
            self._reflections_path.write_text(
                json.dumps(self.reflections, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to save reflections to %s", self._reflections_path)

    # ------------------------------------------------------------------
    # Memory helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Prepend stored reflections to the base ReAct system prompt."""
        if not self.reflections:
            return self._base_system_prompt
        lines = "\n\n".join(f"{i + 1}. {r['text']}" for i, r in enumerate(self.reflections))
        return (
            self._base_system_prompt + "\n\n## Past Game Reflections\n\n"
            "These are lessons distilled from your previous games. "
            "Keep them in mind when making decisions this game.\n\n" + lines
        )

    def _reset_messages(self) -> None:
        self._messages = [{"role": "system", "content": self._build_system_prompt()}]

    # ------------------------------------------------------------------
    # Reflexion interface (from stub)
    # ------------------------------------------------------------------

    def _retrieve_reflections(self, obs: State, info: dict[str, Any]) -> list[str]:
        """Return all stored reflections in chronological order."""
        return [r["text"] for r in self.reflections]

    def _evaluate_game(self, result: str, game_trace: GameTrace | None = None) -> str:
        """Generate a verbal self-reflection on the completed game.

        Args:
            result:     "win", "loss", or "draw".
            game_trace: Structured trace from TraceRecorder (preferred); falls
                        back to _last_game_history if not provided.

        Returns:
            A 2–4 sentence reflection string.
        """
        if game_trace is not None and game_trace.turns:
            history_text = "\n".join(
                f"Turn {t.turn_number} (step {t.timestep})"
                f" | prizes {t.my_prizes}v{t.opp_prizes}"
                f" | {t.my_active.name if t.my_active else '?'}"
                f" vs {t.opp_active.name if t.opp_active else '?'}"
                + (f" [opp scored!]" if t.opp_scored else "")
                + f"\n  Thought: {t.thought}\n  Action:  {t.action}"
                for t in game_trace.turns
            )
        elif self._last_game_history:
            history_text = "\n".join(
                f"Turn {i + 1}: Thought: {entry['thought']} | Action: {entry['action']}"
                for i, entry in enumerate(self._last_game_history)
            )
        else:
            return f"Game ended ({result}) with no recorded turns."

        prompt = _EVAL_PROMPT.format(result=result, history_text=history_text)
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_completion_tokens=512,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception:
            logger.exception("Reflexion evaluation LLM call failed")
            return f"Game ended ({result}). Evaluation unavailable."

    def _store_reflection(self, reflection: str) -> None:
        """Store a reflection in memory and persist to disk, evicting the oldest if at capacity."""
        self.reflections.append({"text": reflection})
        if len(self.reflections) > self.max_reflections:
            self.reflections.pop(0)
        self._save_reflections()

    # ------------------------------------------------------------------
    # Observation helpers
    # ------------------------------------------------------------------

    def _build_user_message(self, observation: StateObservation) -> str:
        return encode(
            observation.model_dump(exclude_none=True, exclude_defaults=True, exclude=_OBS_EXCLUDE)
        )

    def _truncate_history(self) -> None:
        """Keep conversation within max_messages, preserving the system prompt."""
        while len(self._messages) > self.max_messages:
            if len(self._messages) <= 1:
                break
            self._messages.pop(1)
            # Clean up orphaned tool responses that had no parent assistant message
            while len(self._messages) > 1 and self._messages[1].get("role") == "tool":
                self._messages.pop(1)

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def predict(self, obs: State, info: dict[str, Any]) -> Action:
        """Run one ReAct step with reflection-augmented context.

        Reflections from past games are already embedded in the system prompt.
        The loop is identical to ReActAgent; the difference is the system prompt.

        Args:
            obs:  Current game state.
            info: Additional information dictionary.

        Returns:
            The chosen action.
        """
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
            response = self._client.chat.completions.create(
                model=self.model,
                messages=self._messages,
                temperature=self.temperature,
                tools=self._tool_schemas,
                tool_choice="auto",
            )
            message = response.choices[0].message
            thought = message.content or ""

            # ---- no tool calls: nudge the LLM to act ----
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

            # ---- persist assistant message with tool calls ----
            self._messages.append(assistant_message_to_history(message))

            action_to_return: Action | None = None
            for tool_call in message.tool_calls:
                tool_name, arguments = parse_tool_call_arguments(tool_call)

                # Query tools — return info and continue the loop
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

                # Game action tools
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
                        # Failed match — give correction feedback and retry
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

        # Fallback: random action after all retries exhausted
        logger.warning("Reflexion agent falling back to random action")
        self._last_game_history.append({"thought": "fallback", "action": "random"})
        self.trace_recorder.record_turn(observation, "fallback", "random")
        return random.choice(available)

    def on_game_end(self, result: str) -> None:
        """Called when a game ends. Saves reflection to a per-game pending file.

        Writing to a unique file (rather than reflections.json directly) avoids
        race conditions when multiple per-game instances run concurrently within
        a batch. post_batch() consolidates these into reflections.json.
        """
        game_trace = self.trace_recorder.finalize(
            result=result,
            my_deck=self._battle_record.my_deck if self._battle_record else "",
            opp_deck=self._battle_record.opponent_deck if self._battle_record else "",
        )
        if self._battle_record is not None:
            game_trace.save(self._battle_record.record_dir / "trace.json")

        reflection = self._evaluate_game(result, game_trace)
        self._store_reflection(reflection)
        self._pending_dir.mkdir(parents=True, exist_ok=True)
        pending_file = self._pending_dir / f"{uuid.uuid4()}.json"
        try:
            pending_file.write_text(
                json.dumps({"text": reflection}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to save pending reflection to %s", pending_file)
        self._last_game_history.clear()
        self.trace_recorder.reset()

    def reset(self) -> None:
        """Reset per-game state. Reflections persist across games."""
        self._last_game_history.clear()
        self.trace_recorder.reset()
        self._reset_messages()

    def notify_game_start(
        self,
        my_deck: str,
        opponent_deck: str,
        opponent_name: str = "",
    ) -> None:
        """Create a new BattleRecord and reset context for a new game."""
        self._turn_count = 0
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
        """Consolidate per-game pending reflections into persistent memory.

        Called once per batch by eval_pipeline on the persistent batch_agents
        instance, after all per-game instances have finished and written their
        pending reflection files.
        """
        if not self._pending_dir.is_dir():
            return {"reflections_added": 0}

        pending_files = sorted(self._pending_dir.glob("*.json"))
        added = 0
        for f in pending_files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "text" in data:
                    self.reflections.append(data)
                    added += 1
            except Exception:
                logger.exception("Failed to load pending reflection from %s", f)

        if len(self.reflections) > self.max_reflections:
            self.reflections = self.reflections[-self.max_reflections :]

        if added:
            self._save_reflections()
            print(f"  {self.name} evolved: {added} reflections added")

        for f in pending_files:
            try:
                f.unlink()
            except Exception:
                pass

        return {"reflections_added": added}

    def close(self, result: str = "", my_prizes: int = 0, opponent_prizes: int = 0) -> None:
        """Write battle summary at game end."""
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
