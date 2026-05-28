from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from toon_format import encode

from ptcgbench.agents.base_agent import BaseAgent
from ptcgbench.agents.common.deck_composition import read_deck_text
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
from ptcgbench.agents.memory.context_manager import ContextManager
from ptcgbench.agents.memory.reflection_agent import ReflectionAgent
from ptcgbench.agents.skills.skill_registry import SkillRegistry
from ptcgbench.agents.skills.skill_writer import SkillWriter
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


def _render_system_prompt(**kwargs: Any) -> str:
    template = _jinja_env.get_template("system/skillevolving.md")
    return template.render(**kwargs)


class SkillEvolvingAgent(BaseAgent):
    def __init__(
        self,
        model: str = "deepseek-chat",
        seed: int | None = None,
        temperature: float = 0.8,
        max_completion_tokens: int = 2048,
        max_retries: int = 2,
        max_tokens: int = 80000,
        max_messages: int = 40,
    ):
        self.model = model
        self.seed = seed
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.max_messages = max_messages

        # Agent profile
        self.name = f"skillevolving_{model}"
        self.profile = AgentProfile(name=self.name)
        self.profile.save_config(
            AgentConfig(
                name=self.name,
                model=self.model,
                architecture="skillevolving",
                temperature=self.temperature,
                max_completion_tokens=self.max_completion_tokens,
                max_retries=self.max_retries,
                max_tokens=self.max_tokens,
            )
        )

        self._client = build_client(self.model)
        self._tool_schemas = get_tool_schemas()

        # Skills
        self._skill_registry = SkillRegistry(self.profile.skills_dir)
        self._skill_catalog = self._skill_registry.build_catalog()
        self._my_deck_composition = "Unknown."
        self._system_prompt = _render_system_prompt(
            skill_catalog=self._skill_catalog,
            my_deck_composition=self._my_deck_composition,
        )

        self.observer = StateObserver()
        self.executor = ToolCallExecutor()
        self.tool_dispatcher = ToolDispatcher(
            skill_registry=self._skill_registry,
            observer=self.observer,
        )
        self.context_manager = ContextManager(
            model=self.model,
            system_prompt=self._system_prompt,
            max_tokens=self.max_tokens,
            max_messages=self.max_messages,
        )
        self.reflection_agent = ReflectionAgent(
            model=self.model,
            knowledge_base_file=str(self.profile.memory_dir / "knowledge_base.json"),
        )
        self._skill_writer = SkillWriter(
            model=self.model,
            skills_dir=self.profile.skills_dir,
        )

        # Battle state
        self._battle_record: BattleRecord | None = None
        self._turn_count: int = 0
        self.trace_recorder = TraceRecorder()

    def predict(self, obs: State, info: dict[str, Any]) -> Action:
        available = info.get("raw_available_actions", [])
        observation = self.observer.observe(obs, info, available_actions=available)

        # Hidden card selection (e.g. prize cards) — random pick, no need to call LLM
        prompt = info.get("prompt")
        if prompt and getattr(prompt, "hidden", False):
            return random.choice(available)

        # Track turn count for battle record
        turn_number = getattr(obs, "turn_number", 0)
        if turn_number > self._turn_count:
            self._turn_count = turn_number

        user_message = self._build_user_message(observation)
        self.context_manager.add_message({"role": "user", "content": user_message})

        attempt = 0
        while attempt < self.max_retries:
            messages = self.context_manager.build_messages()
            response = chat_completion_with_retry(
                self._client,
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_completion_tokens=self.max_completion_tokens,
                tools=self._tool_schemas,
                tool_choice="auto",
            )

            message = response.choices[0].message
            thought = message.content or ""
            tool_calls = message.tool_calls

            if not tool_calls:
                self.context_manager.add_message(assistant_message_to_history(message))
                attempt += 1
                continue

            self.context_manager.add_message(assistant_message_to_history(message))

            for tool_call in tool_calls:
                tool_name, arguments = parse_tool_call_arguments(tool_call)

                if tool_name == "activate_skill":
                    content = self.tool_dispatcher.activate_skill(
                        arguments.get("name", ""), arguments.get("resource")
                    )
                    self.context_manager.add_skill(content)
                    self.context_manager.add_message(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "content": f"Skill activated. Instructions loaded into context.",
                        }
                    )
                    continue

                if is_general_tool(tool_name):
                    tool_response = self.tool_dispatcher.dispatch(tool_name, arguments, obs)
                    tool_response_message = {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "content": tool_response,
                    }
                    self.context_manager.add_message(tool_response_message)
                    continue

                if is_game_action_tool(tool_name):
                    result = self.executor.execute(tool_name, arguments, info)

                    tool_response_message = {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "content": "",
                    }
                    self.context_manager.add_message(tool_response_message)

                    if result.level == "FULL":
                        self.trace_recorder.record_turn(observation, thought, result.action.to_nl())
                        return result.action
                    else:
                        attempt += 1
                        correction = (
                            f"Your action could not be executed.\n"
                            f"Reason: {result.reason}\n"
                            f"Attempt {attempt}/{self.max_retries}. Please try again with a valid action."
                        )
                        self.context_manager.add_message({"role": "user", "content": correction})
                        break

        self.context_manager.add_message({"role": "assistant", "content": "[random fallback]"})
        self.trace_recorder.record_turn(observation, "fallback", "random")
        return random.choice(available)

    def _build_user_message(self, observation: StateObservation) -> str:
        return encode(
            observation.model_dump(exclude_none=True, exclude_defaults=True, exclude=_OBS_EXCLUDE)
        )

    def reset(self) -> None:
        self.context_manager.clear()
        self.tool_dispatcher.reset()
        self.trace_recorder.reset()
        self.context_manager.add_system(self._system_prompt)

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

        self._my_deck_composition = (
            read_deck_text(resolved_my_deck_path) if resolved_my_deck_path else "Unknown."
        )
        self._system_prompt = _render_system_prompt(
            skill_catalog=getattr(self, "_skill_catalog", ""),
            my_deck_composition=self._my_deck_composition,
        )
        self._battle_record = BattleRecord(
            battles_dir=self.profile.battles_dir,
            my_deck=my_deck,
            opponent_deck=opponent_deck,
            agent_name=self.name,
            opponent_name=opponent_name,
            my_deck_path=resolved_my_deck_path,
            opponent_deck_path=resolved_opponent_deck_path,
        )
        self.context_manager.clear()
        self.tool_dispatcher.reset()
        self.context_manager.set_battle_record(self._battle_record)
        self.context_manager.add_system(self._system_prompt)

    def evolve(
        self,
        battle_summary: dict[str, Any] | None = None,
        history_path: Path | None = None,
    ) -> dict[str, Any] | None:
        """Reflect on all battles and update skills. Returns reflection dict or None."""
        history_path = history_path or (
            self._battle_record.record_dir
            if self._battle_record is not None
            else self.profile.battles_dir
        )
        if not history_path.is_dir():
            logger.info("Skipping evolve: history path does not exist: %s", history_path)
            return None
        if not any(history_path.iterdir()):
            logger.info("Skipping evolve: no battle history found in %s", history_path)
            return None

        reflection = self.reflection_agent.reflect(history_path)
        if self._skill_writer is not None and battle_summary is not None:
            self._skill_writer.write(reflection, battle_summary)
        return reflection

    def close(self, result: str = "", my_prizes: int = 0, opponent_prizes: int = 0) -> None:
        if self._battle_record is not None:
            self._battle_record.write_summary(
                result=result or "unknown",
                turn_count=self._turn_count,
                my_prizes_remaining=my_prizes,
                opponent_prizes_remaining=opponent_prizes,
            )
            trace_recorder = getattr(self, "trace_recorder", None)
            if trace_recorder is not None:
                game_trace = trace_recorder.finalize(
                    result=result or "unknown",
                    my_deck=self._battle_record.my_deck,
                    opp_deck=self._battle_record.opponent_deck,
                )
                game_trace.save(self._battle_record.record_dir / "trace.json")
                trace_recorder.reset()

    def post_game(self, result: str = "", my_prizes: int = 0, opponent_prizes: int = 0) -> None:
        self.close(result, my_prizes, opponent_prizes)

    def post_batch(
        self,
        battle_summary: dict[str, Any],
        history_path: Path,
    ) -> dict[str, Any] | None:
        reflection = self.evolve(battle_summary=battle_summary, history_path=history_path)
        if reflection:
            print(
                f"  {self.name} evolved: {len(reflection.get('lessons', []))} lessons, "
                f"{len(reflection.get('heuristics', []))} heuristics"
            )
        return reflection
