"""Reflection agent for extracting reusable lessons from completed games."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader
from openai import OpenAI

from ptcgbench.agents.common.deck_composition import read_deck_compositions, read_deck_text
from ptcgbench.agents.common.model_client import build_client, chat_completion_with_retry
from ptcgbench.agents.memory.summary_agent import SummaryAgent
from ptcgbench.agents.trace.schema import GameTrace

if TYPE_CHECKING:
    from ptcgbench.agents.skills.skill_writer import SkillWriter

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    keep_trailing_newline=True,
)


def _extract_json_object(content: str) -> dict[str, Any]:
    if not content:
        raise ValueError("Reflection model returned empty content.")

    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Reflection model response does not contain a JSON object.")
    return json.loads(text[start : end + 1])


def _render_reflection_prompt(**kwargs: Any) -> str:
    template = _jinja_env.get_template("reflection/main.md")
    return template.render(**kwargs)


def _render_merge_prompt(**kwargs: Any) -> str:
    template = _jinja_env.get_template("reflection/merge.md")
    return template.render(**kwargs)


class ReflectionAgent:
    def __init__(
        self,
        model: str = "deepseek-chat",
        knowledge_base_file: str = "knowledge_base.json",
        temperature: float = 0.3,
        max_completion_tokens: int = 1400,
        max_turns: int = 200,
        client: OpenAI | None = None,
        skill_writer: SkillWriter | None = None,
        segment_token_budget: int = 60000,
        consolidation_max_tokens: int = 2000,
        summary_max_completion_tokens: int = 1200,
    ):
        self.model = model
        self.knowledge_base_file = Path(knowledge_base_file)
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.max_turns = max_turns
        self.skill_writer = skill_writer
        self.segment_token_budget = segment_token_budget
        self.consolidation_max_tokens = consolidation_max_tokens
        self._client = client or build_client(self.model)
        self.summary_agent = SummaryAgent(
            model=self.model,
            temperature=self.temperature,
            max_completion_tokens=summary_max_completion_tokens,
            client=self._client,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reflect(self, history_path: str | Path) -> dict[str, Any]:
        """Reflect on game history and merge lessons into the knowledge base.

        *history_path* can point to either a single ``.jsonl`` conversation
        file or a battles directory containing ``*/trace.json`` files.
        """
        path = Path(history_path)

        if path.is_dir():
            traces, my_deck_composition, opponent_deck_composition = (
                self._load_traces_from_directory(path)
            )
            if not traces:
                return {
                    "summary": "No battle history found.",
                    "lessons": [],
                    "heuristics": [],
                }
            history_text = self._format_traces(traces, self.max_turns)
        else:
            history = self._load_from_file(path)
            history_text = self.summary_agent.compress(history, self.max_turns)
            my_deck_composition, opponent_deck_composition = read_deck_compositions(path)

        token_count = SummaryAgent.count_tokens(history_text)
        logger.info(
            "Reflection text token count: %d (budget: %d)", token_count, self.segment_token_budget
        )

        if token_count <= self.segment_token_budget:
            prompt = _render_reflection_prompt(
                history_text=history_text,
                my_deck_composition=my_deck_composition,
                opponent_deck_composition=opponent_deck_composition,
            )
            reflection = self._generate_reflection(prompt)
        else:
            logger.info(
                "Reflection text (%d tokens) exceeds budget (%d), using chunked path.",
                token_count,
                self.segment_token_budget,
            )
            reflection = self._reflect_chunked(
                history_text,
                my_deck_composition=my_deck_composition,
                opponent_deck_composition=opponent_deck_composition,
            )

        self._merge_into_knowledge_base(reflection, path)
        return reflection
        # return reflection | {
        #     "knowledge_base_path": str(self.knowledge_base_file),
        #     "entries": self._merge_into_knowledge_base(reflection, path),
        # }

    # ------------------------------------------------------------------
    # History loading
    # ------------------------------------------------------------------

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
        return messages

    def _load_from_file(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise FileNotFoundError(f"History file not found: {path}")
        return self._read_jsonl(path)

    def _load_from_directory(self, battles_dir: Path) -> list[dict[str, Any]]:
        if not battles_dir.is_dir():
            return []
        all_messages: list[dict[str, Any]] = []
        for conv_file in sorted(battles_dir.rglob("conversation.jsonl")):
            all_messages.extend(self._read_jsonl(conv_file))
        return all_messages

    def _load_traces_from_directory(self, battles_dir: Path) -> tuple[list[GameTrace], str, str]:
        """Load GameTrace objects from trace.json files; also return deck compositions."""
        if not battles_dir.is_dir():
            return [], "Unknown.", "Unknown."

        traces: list[GameTrace] = []
        my_deck_text = "Unknown."
        opponent_deck_text = "Unknown."

        for trace_file in sorted(battles_dir.rglob("trace.json")):
            try:
                traces.append(GameTrace.load(trace_file))
            except Exception:
                logger.warning("Failed to load trace from %s", trace_file)
                continue
            # Read deck card lists from the first successfully-loaded battle directory
            if my_deck_text == "Unknown.":
                record_dir = trace_file.parent
                my_path = record_dir / "my_deck.txt"
                opp_path = record_dir / "opponent_deck.txt"
                if my_path.exists():
                    my_deck_text = read_deck_text(my_path)
                if opp_path.exists():
                    opponent_deck_text = read_deck_text(opp_path)

        return traces, my_deck_text, opponent_deck_text

    @staticmethod
    def _format_traces(traces: list[GameTrace], max_turns: int = 200) -> str:
        """Render a list of GameTrace objects into a plain-text history string."""
        parts: list[str] = []
        total = 0

        for i, trace in enumerate(traces):
            s = trace.summary
            result_str = s.result.upper() if s else "?"
            matchup = f"{s.my_deck} vs {s.opp_deck}" if s else ""
            parts.append(f"=== Game {i + 1} [{result_str}] {matchup} ===")

            for t in trace.turns:
                if total >= max_turns:
                    break
                line = (
                    f"T{t.turn_number} step={t.timestep}"
                    f" [me:{t.my_prizes} opp:{t.opp_prizes}]"
                    f" {t.my_active.name if t.my_active else '?'}"
                    f" vs {t.opp_active.name if t.opp_active else '?'}"
                )
                if t.my_scored:
                    line += " [I scored]"
                if t.opp_scored:
                    line += " [opp scored]"
                line += f"\n  Thought: {t.thought.strip()}\n  Action:  {t.action.strip()}"
                parts.append(line)
                total += 1

            if total >= max_turns:
                break

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Prompt building & LLM call
    # ------------------------------------------------------------------

    def _generate_reflection(self, prompt: str) -> dict[str, Any]:
        response = chat_completion_with_retry(
            self._client,
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": "Please produce the JSON reflection based on the instructions above.",
                },
            ],
            temperature=self.temperature,
            max_completion_tokens=self.max_completion_tokens,
        )
        content = response.choices[0].message.content or ""
        reflection = _extract_json_object(content)
        return self._normalize_reflection(reflection)

    # ------------------------------------------------------------------
    # Segmentation
    # ------------------------------------------------------------------

    def _segment_reflection_text(self, text: str) -> list[str]:
        """Split *text* into segments within ``segment_token_budget``.

        Events are never split across segments.  A single oversized event
        becomes its own segment rather than being dropped.
        """
        events = [line for line in text.splitlines() if line.strip()]
        if not events:
            return [text] if text.strip() else []

        segments: list[str] = []
        current_lines: list[str] = []
        current_tokens = 0

        for event in events:
            event_tokens = SummaryAgent.count_tokens(event)

            # Oversized event: flush current segment, start a new one
            if event_tokens > self.segment_token_budget:
                if current_lines:
                    segments.append("\n".join(current_lines))
                    current_lines = []
                    current_tokens = 0
                segments.append(event)
                continue

            # Adding this event would exceed budget: flush current segment
            if current_tokens + event_tokens > self.segment_token_budget and current_lines:
                segments.append("\n".join(current_lines))
                current_lines = []
                current_tokens = 0

            current_lines.append(event)
            current_tokens += event_tokens

        if current_lines:
            segments.append("\n".join(current_lines))

        return segments

    # ------------------------------------------------------------------
    # Chunked reflection
    # ------------------------------------------------------------------

    def _reflect_chunked(
        self,
        history_text: str,
        my_deck_composition: str = "Unknown.",
        opponent_deck_composition: str = "Unknown.",
    ) -> dict[str, Any]:
        """Reflect on history by splitting into segments and consolidating results."""
        segments = self._segment_reflection_text(history_text)
        logger.info(
            "Chunked reflection: %d segments, token counts: %s",
            len(segments),
            [SummaryAgent.count_tokens(s) for s in segments],
        )

        per_segment_reflections: list[dict[str, Any]] = []

        for i, segment in enumerate(segments):
            logger.info(
                "Reflecting on segment %d/%d (%d tokens)",
                i + 1,
                len(segments),
                SummaryAgent.count_tokens(segment),
            )
            prompt = _render_reflection_prompt(
                history_text=segment,
                my_deck_composition=my_deck_composition,
                opponent_deck_composition=opponent_deck_composition,
            )
            reflection = self._generate_reflection(prompt)
            per_segment_reflections.append(reflection)

        if len(per_segment_reflections) == 1:
            return per_segment_reflections[0]

        return self._consolidate_reflections(per_segment_reflections)

    # ------------------------------------------------------------------
    # Consolidation
    # ------------------------------------------------------------------

    def _consolidate_reflections(self, reflections: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge per-segment reflections into a single consolidated result."""
        segment_json = json.dumps(reflections, ensure_ascii=False, indent=2)
        logger.info("Consolidating %d per-segment reflections", len(reflections))

        prompt = _render_merge_prompt(segment_reflections=segment_json)
        response = chat_completion_with_retry(
            self._client,
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": "Please consolidate the segment reflections above into one unified JSON.",
                },
            ],
            temperature=self.temperature,
            max_completion_tokens=self.consolidation_max_tokens,
        )
        content = response.choices[0].message.content or ""
        consolidated = _extract_json_object(content)
        return self._normalize_reflection(consolidated)

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize_reflection(self, reflection: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": str(reflection.get("summary", "")).strip(),
            "lessons": self._normalize_lessons(reflection.get("lessons", [])),
            "heuristics": self._normalize_heuristics(reflection.get("heuristics", [])),
        }

    def _normalize_lessons(self, items: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return normalized

        for item in items:
            if not isinstance(item, dict):
                continue
            lesson = str(item.get("lesson", "")).strip()
            if not lesson:
                continue
            normalized.append(
                {
                    "lesson": lesson,
                    "card_names": self._normalize_string_list(item.get("card_names", [])),
                }
            )
        return normalized

    def _normalize_heuristics(self, items: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return normalized

        for item in items:
            if isinstance(item, str):
                heuristic = item.strip()
                if heuristic:
                    normalized.append({"heuristic": heuristic, "card_names": []})
                continue
            if not isinstance(item, dict):
                continue

            heuristic = str(item.get("heuristic", "")).strip()
            if not heuristic:
                continue
            normalized.append(
                {
                    "heuristic": heuristic,
                    "card_names": self._normalize_string_list(item.get("card_names", [])),
                }
            )
        return normalized

    def _normalize_string_list(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [str(value).strip() for value in values if str(value).strip()]

    # ------------------------------------------------------------------
    # Knowledge base
    # ------------------------------------------------------------------

    def _merge_into_knowledge_base(
        self,
        reflection: dict[str, Any],
        history_path: Path,
    ) -> list[dict[str, Any]]:
        knowledge_base = self._load_knowledge_base()
        timestamp = datetime.now(timezone.utc).isoformat()

        sections: list[tuple[str, list[dict[str, Any]]]] = [
            ("lesson", reflection["lessons"]),
            ("heuristic", reflection["heuristics"]),
        ]
        for entry_type, items in sections:
            for item in items:
                entry = {
                    "type": entry_type,
                    "source_file": str(history_path),
                    "created_at": timestamp,
                    **item,
                }
                knowledge_base.append(entry)

        self.knowledge_base_file.parent.mkdir(parents=True, exist_ok=True)
        with self.knowledge_base_file.open("w", encoding="utf-8") as f:
            json.dump(knowledge_base, f, ensure_ascii=False, indent=2)
        return knowledge_base

    def _load_knowledge_base(self) -> list[dict[str, Any]]:
        if not self.knowledge_base_file.exists():
            return []
        with self.knowledge_base_file.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
