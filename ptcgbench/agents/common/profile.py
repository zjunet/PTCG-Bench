"""Agent profile system for managing agent directories, configs, and battle records."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Pydantic model for an agent's config.yaml."""

    name: str
    model: str
    architecture: str
    temperature: float = 0.8
    max_completion_tokens: int = 2048
    max_retries: int = 2
    max_tokens: int = 80000
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentProfile:
    """Manages an agent's directory lifecycle and config on disk."""

    def __init__(self, name: str, root: Path | None = None) -> None:
        self.name = name
        self.root = root or Path(".ptcg") / "agents"
        self.agent_dir = self.root / name.replace("/", "--")
        self.config_path = self.agent_dir / "config.yaml"
        self.decks_dir = self.agent_dir / "decks"
        self.battles_dir = self.agent_dir / "battles"
        self.memory_dir = self.agent_dir / "memory"
        self.skills_dir = self.agent_dir / "skills"

    def ensure_dirs(self) -> None:
        """Create the agent directory structure if it doesn't exist."""
        for d in (self.decks_dir, self.battles_dir, self.memory_dir, self.skills_dir):
            d.mkdir(parents=True, exist_ok=True)

    def save_config(self, config: AgentConfig) -> None:
        """Write config.yaml to the agent directory."""
        self.ensure_dirs()
        self.config_path.write_text(
            yaml.dump(config.model_dump(), default_flow_style=False),
            encoding="utf-8",
        )

    def load_config(self) -> AgentConfig:
        """Read config.yaml from the agent directory."""
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        return AgentConfig.model_validate(data)

    def copy_deck(self, deck_path: str | Path) -> Path:
        """Copy a deck .txt file into the agent's decks/ directory.

        Returns the path to the copied file. No-op if already present.
        """
        deck_path = Path(deck_path)
        self.ensure_dirs()
        # Normalize filename: spaces to underscores, lowercased
        normalized_name = deck_path.name.replace(" ", "_").lower()
        dest = self.decks_dir / normalized_name
        if not dest.exists():
            shutil.copy2(deck_path, dest)
        return dest

    @staticmethod
    def deck_name_from_path(deck_path: str | Path) -> str:
        """Derive deck name from file stem (e.g., 'charizard_ex.txt' → 'charizard-ex')."""
        stem = Path(deck_path).stem
        return stem.replace("_", "-")


class BattleRecord:
    """Represents one game's output under an agent's battles/ directory."""

    def __init__(
        self,
        battles_dir: Path,
        my_deck: str,
        opponent_deck: str,
        agent_name: str = "",
        opponent_name: str = "",
        my_deck_path: str | Path | None = None,
        opponent_deck_path: str | Path | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.opponent_name = opponent_name
        self.my_deck = my_deck
        self.opponent_deck = opponent_deck

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        unique_suffix = uuid4().hex[:8]
        base_name = f"{timestamp}_{unique_suffix}_{my_deck}_vs_{opponent_deck}"
        self.record_dir = self._resolve_unique_dir(battles_dir / base_name)

        self.record_dir.mkdir(parents=True, exist_ok=True)
        self.conversation_path = self.record_dir / "conversation.jsonl"
        self.events_path = self.record_dir / "events.jsonl"
        self.summary_path = self.record_dir / "summary.json"
        self.replay_path = self.record_dir / "replay.jsonl"
        self.replay_text_path = self.record_dir / "replay.txt"

        if my_deck_path:
            src = Path(my_deck_path)
            if src.exists():
                shutil.copy2(src, self.record_dir / "my_deck.txt")
        if opponent_deck_path:
            src = Path(opponent_deck_path)
            if src.exists():
                shutil.copy2(src, self.record_dir / "opponent_deck.txt")

    def _resolve_unique_dir(self, candidate: Path) -> Path:
        """Return candidate if available, otherwise append -2, -3, etc."""
        if not candidate.exists():
            return candidate
        suffix = 2
        while True:
            alt = Path(f"{candidate}-{suffix}")
            if not alt.exists():
                return alt
            suffix += 1

    def append_conversation(self, message: dict[str, Any]) -> None:
        """Append one message to conversation.jsonl incrementally."""
        with self.conversation_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def append_event(self, event: dict[str, Any]) -> None:
        """Append one event to events.jsonl."""
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def save_replay(self, source_path: str | Path) -> None:
        """Copy JSONL replay and its text counterpart into this battle record directory."""
        source_path = Path(source_path)
        if source_path.exists():
            shutil.copy2(source_path, self.replay_path)
        # Also copy the text replay if it exists (same name with _replay.txt suffix)
        text_path = source_path.parent / source_path.name.replace(".jsonl", "_replay.txt")
        if text_path.exists():
            shutil.copy2(text_path, self.replay_text_path)

    def write_summary(
        self,
        result: str,
        turn_count: int,
        my_prizes_remaining: int,
        opponent_prizes_remaining: int,
    ) -> None:
        """Write summary.json with game outcome metadata."""
        summary = {
            "agent_name": self.agent_name,
            "opponent_name": self.opponent_name,
            "my_deck": self.my_deck,
            "opponent_deck": self.opponent_deck,
            "result": result,
            "turn_count": turn_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "my_prizes_remaining": my_prizes_remaining,
            "opponent_prizes_remaining": opponent_prizes_remaining,
        }
        self.summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
