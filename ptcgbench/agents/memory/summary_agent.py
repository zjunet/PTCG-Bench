"""Summary agent for compressing conversation history into turn summaries."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import json_repair
import tiktoken
import weave
from jinja2 import Environment, FileSystemLoader
from openai import OpenAI

from ptcgbench.agents.common.model_client import build_client, chat_completion_with_retry

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    keep_trailing_newline=True,
)

_TURN_NUMBER_RE = re.compile(r"\bturn_number\s*:\s*(\d+)\b")
_TIMESTEP_RE = re.compile(r"\btimestep\s*:\s*(\d+)\b")
_TURN_RE = re.compile(r"\bturn\s*:\s*([^\n]+)")
_RETRY_PREFIXES = (
    "Please select an action using one of the available tools.",
    "Your action could not be executed.",
)


def _extract_json_object(content: str) -> dict[str, Any]:
    if not content:
        raise ValueError("Summary model returned empty content.")

    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Summary model response does not contain a JSON object.")
    return json_repair.loads(text[start : end + 1])


def _render_summary_prompt(**kwargs: Any) -> str:
    template = _jinja_env.get_template("summary/main.md")
    return template.render(**kwargs)


class SummaryAgent:
    """Compresses conversation history into turn-level JSONL summaries."""

    _ENCODING = "cl100k_base"

    def __init__(
        self,
        model: str = "deepseek-chat",
        temperature: float = 0.1,
        max_completion_tokens: int = 1200,
        summary_max_workers: int = 8,
        client: OpenAI | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.summary_max_workers = max(1, summary_max_workers)
        self._client = client or build_client(self.model)

    @staticmethod
    def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
        """Return the number of tokens in *text* using tiktoken."""
        enc = tiktoken.get_encoding(encoding_name)
        return len(enc.encode(text))

    @weave.op
    def compress(
        self,
        messages: list[dict[str, Any]],
        max_turns: int,
    ) -> str:
        """Return turn-summary JSONL text for *messages*."""
        if not messages:
            return "(no history)"

        turns = self._group_messages_by_turn(messages)
        if not turns:
            return "(no history)"

        recent_turns = turns[-max_turns:] if max_turns > 0 else turns
        lines: list[str] = []
        if len(recent_turns) == 1 or self.summary_max_workers == 1:
            summaries = [self._summarize_turn(turn["messages"]) for turn in recent_turns]
        else:
            max_workers = min(self.summary_max_workers, len(recent_turns))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                summaries = list(executor.map(self._summarize_grouped_turn, recent_turns))

        for turn, summary in zip(recent_turns, summaries, strict=True):
            line = {
                "type": "turn_summary",
                "turn_number": turn["turn_number"],
                "timestep": turn["timestep"],
                "summary": summary,
            }
            lines.append(json.dumps(line, ensure_ascii=False))

        return "\n".join(lines)

    def _summarize_grouped_turn(self, turn: dict[str, Any]) -> dict[str, Any]:
        return self._summarize_turn(turn["messages"])

    def _group_messages_by_turn(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        turns: list[dict[str, Any]] = []
        current_turn: dict[str, Any] | None = None

        for message in messages:
            role = message.get("role", "")
            if role == "system":
                continue

            if role == "user":
                content = str(message.get("content", ""))
                turn = self._extract_turn(message)
                turn_number = self._extract_turn_number(message)
                timestep = self._extract_timestep(message)

                if turn_number is not None:
                    if (
                        current_turn is not None
                        and current_turn["messages"]
                        and current_turn["turn_number"] == turn_number
                        and current_turn["turn"] == turn
                    ):
                        current_turn["messages"].append(message)
                        current_turn["timestep"] = timestep
                    else:
                        if current_turn and current_turn["messages"]:
                            turns.append(current_turn)
                        current_turn = {
                            "turn": turn,
                            "turn_number": turn_number,
                            "timestep": timestep,
                            "messages": [message],
                        }
                    continue

                if self._is_retry_or_correction(content):
                    if current_turn is not None:
                        current_turn["messages"].append(message)
                    continue

            if current_turn is None:
                current_turn = {
                    "turn": None,
                    "turn_number": None,
                    "timestep": None,
                    "messages": [],
                }
            current_turn["messages"].append(message)

        if current_turn and current_turn["messages"]:
            turns.append(current_turn)

        return turns

    def _summarize_turn(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        turn_text = "\n".join(json.dumps(message, ensure_ascii=False) for message in messages)
        prompt = _render_summary_prompt(chat_history=turn_text)
        response = chat_completion_with_retry(
            self._client,
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": "Please summarize this single turn into the required JSON.",
                },
            ],
            temperature=self.temperature,
            max_completion_tokens=self.max_completion_tokens,
        )
        content = response.choices[0].message.content or ""
        return _extract_json_object(content)

    def _extract_turn(self, message: dict[str, Any]) -> str | None:
        content = str(message.get("content", ""))
        match = _TURN_RE.search(content)
        return match.group(1).strip() if match else None

    def _extract_turn_number(self, message: dict[str, Any]) -> int | None:
        content = str(message.get("content", ""))
        match = _TURN_NUMBER_RE.search(content)
        return int(match.group(1)) if match else None

    def _extract_timestep(self, message: dict[str, Any]) -> int | None:
        content = str(message.get("content", ""))
        match = _TIMESTEP_RE.search(content)
        return int(match.group(1)) if match else None

    def _is_retry_or_correction(self, content: str) -> bool:
        return any(content.startswith(prefix) for prefix in _RETRY_PREFIXES)
