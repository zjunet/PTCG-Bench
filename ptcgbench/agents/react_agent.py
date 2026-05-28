"""ReAct (Reasoning + Acting) agent for PTCG battles.

Follows the ReAct loop: Thought -> Action -> Observation -> Thought -> ...
Each step produces a reasoning trace before selecting an action.
"""

from __future__ import annotations

import logging
import random
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
from ptcgbench.agents.trace import TraceRecorder
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


def _render_system_prompt() -> str:
    template = _jinja_env.get_template("system/react.md")
    return template.render()


class ReActAgent(BaseAgent):
    """Agent that alternates between reasoning and action selection.

    The ReAct pattern decomposes decision-making into:
    - Thought: analyze the current game state
    - Action: select from available actions based on reasoning
    - Observation: (next turn) see the result and continue the loop
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_retries: int = 3,
        max_messages: int = 40,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.max_messages = max_messages
        self.trace: list[dict[str, str]] = []
        self.trace_recorder = TraceRecorder()

        # Agent profile
        self.name = f"react_{model}"
        self.profile = AgentProfile(name=self.name)
        self.profile.save_config(
            AgentConfig(
                name=self.name,
                model=self.model,
                architecture="react",
                temperature=self.temperature,
                max_retries=self.max_retries,
            )
        )

        # Battle state
        self._battle_record: BattleRecord | None = None
        self._turn_count: int = 0

        # LLM client
        self._client = build_client(model)

        # Reusable components
        self.observer = StateObserver()
        self.executor = ToolCallExecutor()
        self.tool_dispatcher = ToolDispatcher(observer=self.observer)
        self._tool_schemas = get_tool_schemas()

        # Conversation history
        self._system_prompt = _render_system_prompt()
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
        ]

    # ------------------------------------------------------------------
    # Internal helpers
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
            # If we removed the parent assistant, clean up orphaned tool responses
            while len(self._messages) > 1 and self._messages[1].get("role") == "tool":
                self._messages.pop(1)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def predict(self, obs: State, info: dict[str, Any]) -> Action:
        """Run one ReAct step: think then act.

        Args:
            obs: Current game state.
            info: Additional information dictionary.

        Returns:
            The chosen action.
        """
        available = info.get("raw_available_actions", [])
        if not available:
            raise ValueError("No available actions")
        observation = self.observer.observe(obs, info, available_actions=available)

        # Hidden card selection (e.g. prize cards) — random pick, no need to call LLM
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

            # ---- no tool calls: prompt the LLM to act ----
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

                # Query tools — fetch info, then continue the ReAct loop
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
                            self.trace.append(
                                {
                                    "thought": thought,
                                    "action": result.action.to_nl(),
                                }
                            )
                            self.trace_recorder.record_turn(
                                observation, thought, result.action.to_nl()
                            )
                    else:
                        # Failed match — give correction feedback
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
        logger.warning("ReAct agent falling back to random action")
        self.trace.append({"thought": "fallback", "action": "random"})
        self.trace_recorder.record_turn(observation, "fallback", "random")
        return random.choice(available)

    def reset(self) -> None:
        """Clear reasoning trace and conversation history between games."""
        self.trace.clear()
        self.trace_recorder.reset()
        self._messages = [{"role": "system", "content": self._system_prompt}]

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

    def close(self, result: str = "", my_prizes: int = 0, opponent_prizes: int = 0) -> None:
        """Write battle summary and trace at game end."""
        if self._battle_record is not None:
            self._battle_record.write_summary(
                result=result or "unknown",
                turn_count=self._turn_count,
                my_prizes_remaining=my_prizes,
                opponent_prizes_remaining=opponent_prizes,
            )
            game_trace = self.trace_recorder.finalize(
                result=result or "unknown",
                my_deck=self._battle_record.my_deck,
                opp_deck=self._battle_record.opponent_deck,
            )
            game_trace.save(self._battle_record.record_dir / "trace.json")

    def post_game(self, result: str = "", my_prizes: int = 0, opponent_prizes: int = 0) -> None:
        self.close(result, my_prizes, opponent_prizes)
