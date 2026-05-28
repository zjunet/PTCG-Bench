from __future__ import annotations

from typing import Any, Dict, List

import tiktoken

from ptcgbench.agents.common.profile import BattleRecord


class ContextManager:
    def __init__(
        self,
        model: str,
        system_prompt: str,
        max_tokens: int,
        max_messages: int | None = None,
    ):
        self.messages: List[Dict[str, Any]] = []
        self._skill_messages: list[str] = []
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._max_messages = max_messages
        self._battle_record: BattleRecord | None = None
        try:
            self._encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            self._encoding = tiktoken.get_encoding("cl100k_base")

        self.add_system(system_prompt)

    def set_battle_record(self, record: BattleRecord) -> None:
        """Set the active battle record for incremental conversation writing."""
        self._battle_record = record

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            total += 4
            for key, value in msg.items():
                if value is None:
                    continue
                if isinstance(value, str):
                    total += len(self._encoding.encode(value))
                elif key == "tool_calls" and isinstance(value, list):
                    for tc in value:
                        if isinstance(tc, dict):
                            func = tc.get("function", {})
                            total += len(self._encoding.encode(func.get("name", "")))
                            total += len(self._encoding.encode(func.get("arguments", "")))
        return total

    def add_system(self, content: str) -> None:
        self.messages.append({"role": "system", "content": content})
        if self._battle_record is not None:
            self._battle_record.append_conversation({"role": "system", "content": content})

    def add_message(self, messages: dict[str, Any]) -> None:
        self.messages.append(messages)
        if self._battle_record is not None:
            self._battle_record.append_conversation(messages)

    def add_skill(self, content: str) -> None:
        """Store activated skill content separately from the main message list."""
        self._skill_messages.append(content)
        if self._battle_record is not None:
            self._battle_record.append_conversation({"role": "system", "content": content})

    def build_messages(self) -> list[dict[str, Any]]:
        self._truncate_if_needed()
        if not self._skill_messages:
            return self.messages
        # Insert skill messages right after the system prompt.
        result: list[dict[str, Any]] = []
        inserted = False
        for msg in self.messages:
            if not inserted and msg.get("role") != "system":
                for skill in self._skill_messages:
                    result.append({"role": "system", "content": skill})
                inserted = True
            result.append(msg)
        if not inserted:
            # All messages are system messages; append skills at the end.
            for skill in self._skill_messages:
                result.append({"role": "system", "content": skill})
        return result

    def clear(self) -> None:
        self.messages.clear()
        self._skill_messages.clear()
        self._battle_record = None

    def _truncate_if_needed(self) -> None:
        self._truncate_by_message_count()
        self._truncate_by_token_count()

    def _truncate_by_message_count(self) -> None:
        if self._max_messages is None:
            return
        while len(self.messages) > self._max_messages:
            if not self._drop_oldest_removable_message():
                break

    def _truncate_by_token_count(self) -> None:
        if self.count_tokens(self.messages) < self._max_tokens:
            return

        while self.count_tokens(self.messages) >= self._max_tokens:
            if not self._drop_oldest_removable_message():
                break

    def _drop_oldest_removable_message(self) -> bool:
        """Remove the oldest non-system message and any orphaned tool replies."""
        if len(self.messages) <= 1:
            return False

        self.messages.pop(1)
        # A tool message without its parent assistant is invalid.
        while len(self.messages) > 1 and self.messages[1].get("role") == "tool":
            self.messages.pop(1)
        return True
