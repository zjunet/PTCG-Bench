"""Long-Term Memory Agent for PTCG battles.

Extends ReActAgent with a two-layer memory system:

  Game-level  — After each game, an LLM call distils the reasoning trace into
                3–8 strategic and tactical memory entries and writes them to a
                persistent JSON store.

  Round-level — The extraction prompt groups decisions by step, so the LLM
                naturally produces both coarse (game-wide) and fine (per-turn)
                insights without requiring extra LLM calls during play.

At each decision step, the agent:
  1. Builds retrieval tags from the current StateObservation.
  2. Scores every stored memory by tag overlap.
  3. Prepends the top-k memories to the user message so the LLM sees them
     before reasoning about the action.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader

from ptcgbench.agents.common.profile import AgentConfig, AgentProfile, BattleRecord
from ptcgbench.agents.interfaces.schema import StateObservation
from ptcgbench.agents.memory.long_term_memory import (
    MemoryEntry,
    MemoryRetriever,
    MemoryStore,
    MemoryWriter,
)
from ptcgbench.agents.react_agent import ReActAgent
from ptcg.utils.load_deck import _resolve_deck_path

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    keep_trailing_newline=True,
)


def _render_system_prompt() -> str:
    template = _jinja_env.get_template("system/ltm.md")
    return template.render()


class LTMAgent(ReActAgent):
    """ReAct agent augmented with a persistent long-term memory store.

    Memory lifecycle:
    - ``notify_game_start`` resets in-game state and records deck info.
    - ``_build_user_message`` retrieves top-k memories and injects them.
    - ``post_game`` runs the MemoryWriter to extract and persist new entries.

    Args:
        model:           LLM model identifier.
        temperature:     Sampling temperature for the main agent.
        max_retries:     Max tool-call retry attempts per decision step.
        max_messages:    Sliding-window message history length.
        top_k_memories:  Number of memories to inject per decision step.
        writer_temperature: Sampling temperature for the memory extraction LLM.
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_retries: int = 3,
        max_messages: int = 40,
        top_k_memories: int = 3,
        writer_temperature: float = 0.3,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            max_messages=max_messages,
            **kwargs,
        )

        # Override identity so profile/memory dirs are separate from react_*
        self.name = f"ltm_{model}"
        self.profile = AgentProfile(name=self.name)
        self.profile.save_config(
            AgentConfig(
                name=self.name,
                model=self.model,
                architecture="ltm",
                temperature=self.temperature,
                max_retries=self.max_retries,
            )
        )

        # Memory components
        self._memory_store = MemoryStore(self.profile.memory_dir / "long_term_memory.json")
        self._retriever = MemoryRetriever(self._memory_store)
        self._memory_writer = MemoryWriter(
            model=model,
            temperature=writer_temperature,
        )
        self._top_k = top_k_memories

        # Game-scoped metadata used by the memory writer
        self._my_deck: str = ""
        self._opponent_deck: str = ""
        self._game_id: str = ""

        # Use the LTM system prompt (extends react.md with memory instructions)
        self._system_prompt = _render_system_prompt()
        self._messages = [{"role": "system", "content": self._system_prompt}]

    # ------------------------------------------------------------------
    # Memory injection — overrides parent's message builder
    # ------------------------------------------------------------------

    def _build_user_message(self, observation: StateObservation) -> str:
        base = super()._build_user_message(observation)

        query_tags = MemoryRetriever.build_query_tags(observation)
        memories = self._retriever.retrieve(query_tags, top_k=self._top_k)

        if not memories:
            return base

        memory_block = self._format_memories(memories, query_tags)
        return memory_block + "\n\n" + base

    @staticmethod
    def _format_memories(memories: list[MemoryEntry], query_tags: dict[str, str]) -> str:
        tag_summary = (
            f"phase={query_tags.get('phase', '?')}  "
            f"prize_delta={query_tags.get('prize_delta', '?')}  "
            f"my_active={query_tags.get('my_active', '?')}  "
            f"opp_active={query_tags.get('opp_active', '?')}  "
            f"decision={query_tags.get('decision_type', '?')}"
        )
        lines = [f"[PAST EXPERIENCE]  (query: {tag_summary})"]
        for i, mem in enumerate(memories, 1):
            result_badge = f"[{mem.game_result}]" if mem.game_result else ""
            lines.append(f"{i}. {result_badge} {mem.text}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Game lifecycle hooks
    # ------------------------------------------------------------------

    def notify_game_start(
        self,
        my_deck: str,
        opponent_deck: str,
        opponent_name: str = "",
    ) -> None:
        self._my_deck = my_deck
        self._opponent_deck = opponent_deck
        self._game_id = uuid4().hex

        # Resolve deck paths for BattleRecord (same logic as parent)
        try:
            resolved_my: Path | None = _resolve_deck_path(my_deck)
        except FileNotFoundError:
            try:
                resolved_my = _resolve_deck_path(Path(str(my_deck)).stem.replace("-", "_"))
            except FileNotFoundError:
                resolved_my = None

        try:
            resolved_opp: Path | None = _resolve_deck_path(opponent_deck)
        except FileNotFoundError:
            try:
                resolved_opp = _resolve_deck_path(Path(str(opponent_deck)).stem.replace("-", "_"))
            except FileNotFoundError:
                resolved_opp = None

        self._battle_record = BattleRecord(
            battles_dir=self.profile.battles_dir,
            my_deck=my_deck,
            opponent_deck=opponent_deck,
            agent_name=self.name,
            opponent_name=opponent_name,
            my_deck_path=resolved_my,
            opponent_deck_path=resolved_opp,
        )
        self._turn_count = 0
        self.trace.clear()
        self._messages = [{"role": "system", "content": self._system_prompt}]

    def post_game(self, result: str = "", my_prizes: int = 0, opponent_prizes: int = 0) -> None:
        """Write battle summary and extract + persist memory entries."""
        # Parent writes summary.json and saves trace.json
        super().post_game(result, my_prizes, opponent_prizes)

        game_trace = self.trace_recorder.finalize(
            result=result or "unknown",
            my_deck=self._my_deck,
            opp_deck=self._opponent_deck,
        )
        if self._battle_record is not None:
            game_trace.save(self._battle_record.record_dir / "trace.json")

        if not game_trace.turns:
            return

        entries = self._memory_writer.extract(trace=game_trace, game_id=self._game_id)
        if entries:
            self._memory_store.add_many(entries)
            logger.info(
                "LTMAgent: stored %d memory entries (total: %d)",
                len(entries),
                len(self._memory_store),
            )
