"""Long-term memory store and retrieval for PTCG agents.

Two-layer design:
- Game-level: LLM extracts 3-8 strategic + tactical entries after each game.
- Round-level: Lightweight rule-based turn grouping is included in the extraction
  prompt so the LLM naturally produces round-granular insights too.

Retrieval is keyword/tag-based (no embedding API required). Tags capture game
phase, prize delta, active Pokémon names, and decision type.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from ptcgbench.agents.common.model_client import build_client, chat_completion_with_retry
from ptcgbench.agents.interfaces.schema import StateObservation
from ptcgbench.agents.trace.schema import GameTrace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction prompt (inlined — short enough not to need a template file)
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """\
You are a memory distiller for a Pokémon TCG AI agent.
Your task: read a game trace (per-step snapshots with prize counts, active Pokémon, \
thought, and action) and extract concise, actionable memory entries that will help \
the agent make better decisions in future games.

Game metadata:
- My deck:       {my_deck}
- Opponent deck: {opponent_deck}
- Result:        {game_result}

Game trace (ordered by decision step):
{trace_text}

Produce 4–8 memory entries covering both:
1. STRATEGIC insights (game-level): deck matchup patterns, win conditions,
   resource management lessons.
2. TACTICAL insights (round-level): specific turn decisions — when to attack
   vs set up, when to retreat, key supporter timing, etc.

Return ONLY valid JSON in this exact schema — no markdown fences, no extra text:
{{
  "entries": [
    {{
      "text": "1-2 sentence actionable insight describing WHEN and HOW to act",
      "tags": {{
        "phase": "early|mid|late",
        "prize_delta": "<integer: my_prizes_remaining - opp_prizes_remaining>",
        "my_active": "<Pokémon name or empty string>",
        "opp_active": "<Pokémon name or empty string>",
        "decision_type": "attack|attach_energy|supporter|retreat|setup"
      }}
    }}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class MemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    text: str
    tags: dict[str, str] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_game_id: str = ""
    game_result: str = ""  # "win" | "loss" | "draw" | "unknown"


# ---------------------------------------------------------------------------
# Memory store
# ---------------------------------------------------------------------------


class MemoryStore:
    """JSON-backed persistent store for MemoryEntry objects."""

    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path
        self._entries: list[MemoryEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            with self.store_path.open(encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    try:
                        self._entries.append(MemoryEntry.model_validate(item))
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("MemoryStore: could not load %s: %s", self.store_path, exc)

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self.store_path.open("w", encoding="utf-8") as f:
            json.dump(
                [e.model_dump() for e in self._entries],
                f,
                ensure_ascii=False,
                indent=2,
            )

    def add_many(self, entries: list[MemoryEntry]) -> None:
        self._entries.extend(entries)
        self._save()

    @property
    def entries(self) -> list[MemoryEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------


class MemoryRetriever:
    """Score and retrieve memories relevant to the current game state.

    Uses tag-overlap scoring — no external embedding API required.
    """

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    # ------------------------------------------------------------------
    # Query tag extraction from StateObservation
    # ------------------------------------------------------------------

    @staticmethod
    def build_query_tags(obs: StateObservation) -> dict[str, str]:
        """Derive retrieval tags from the current observation."""
        my = obs.my
        opp = obs.opponent
        turn_number = obs.turn_number

        prize_delta = my.prize_count - opp.prize_count

        if turn_number <= 5:
            phase = "early"
        elif turn_number <= 12:
            phase = "mid"
        else:
            phase = "late"

        my_active = my.active[0].name if my.active else ""
        opp_active = opp.active[0].name if opp.active else ""

        available_lower = " ".join(obs.available_actions).lower()
        if "attack" in available_lower:
            decision_type = "attack"
        elif not my.energy_played:
            decision_type = "attach_energy"
        elif not my.supporter_played:
            decision_type = "supporter"
        elif not my.retreated:
            decision_type = "retreat"
        else:
            decision_type = "setup"

        return {
            "phase": phase,
            "prize_delta": str(prize_delta),
            "my_active": my_active,
            "opp_active": opp_active,
            "decision_type": decision_type,
        }

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query_tags: dict[str, str], top_k: int = 3) -> list[MemoryEntry]:
        """Return top-k most relevant entries by tag-overlap scoring."""
        if not self.store.entries:
            return []

        scored: list[tuple[float, MemoryEntry]] = [
            (self._score(query_tags, entry), entry)
            for entry in self.store.entries
            if self._score(query_tags, entry) > 0
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    @staticmethod
    def _score(query: dict[str, str], entry: MemoryEntry) -> float:
        tags = entry.tags
        score = 0.0

        if query.get("phase") == tags.get("phase"):
            score += 2.0

        try:
            q_delta = int(query.get("prize_delta", "99"))
            e_delta = int(tags.get("prize_delta", "99"))
            diff = abs(q_delta - e_delta)
            if diff == 0:
                score += 3.0
            elif diff == 1:
                score += 1.5
        except (ValueError, TypeError):
            pass

        q_my = query.get("my_active", "")
        if q_my and q_my == tags.get("my_active"):
            score += 2.5

        q_opp = query.get("opp_active", "")
        if q_opp and q_opp == tags.get("opp_active"):
            score += 2.5

        if query.get("decision_type") == tags.get("decision_type"):
            score += 2.0

        if entry.game_result == "win":
            score += 0.5

        return score


# ---------------------------------------------------------------------------
# Memory writer
# ---------------------------------------------------------------------------


class MemoryWriter:
    """Extract MemoryEntry objects from a completed game trace via an LLM call."""

    def __init__(
        self,
        model: str = "deepseek-chat",
        temperature: float = 0.3,
        max_completion_tokens: int = 1400,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self._client = build_client(model)

    def extract(
        self,
        trace: GameTrace,
        game_id: str = "",
    ) -> list[MemoryEntry]:
        """Distill a GameTrace into a set of memory entries.

        Args:
            trace:   Finalized GameTrace from TraceRecorder.
            game_id: Unique identifier for the source game.

        Returns:
            List of MemoryEntry objects ready for storage.
        """
        if not trace.turns:
            return []

        s = trace.summary
        game_result = s.result if s else "unknown"
        my_deck = s.my_deck if s else "unknown"
        opponent_deck = s.opp_deck if s else "unknown"

        trace_text = "\n".join(
            f"[Step {i + 1}] T{t.turn_number} [me:{t.my_prizes} opp:{t.opp_prizes}]"
            f" {t.my_active.name if t.my_active else '?'}"
            f" vs {t.opp_active.name if t.opp_active else '?'}"
            + (" [opp scored]" if t.opp_scored else "")
            + f"\n  Thought: {t.thought.strip()}\n  Action:  {t.action.strip()}"
            for i, t in enumerate(trace.turns)
        )

        prompt = _EXTRACT_SYSTEM.format(
            my_deck=my_deck or "unknown",
            opponent_deck=opponent_deck or "unknown",
            game_result=game_result,
            trace_text=trace_text,
        )

        try:
            response = chat_completion_with_retry(
                self._client,
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Extract memory entries as JSON."},
                ],
                temperature=self.temperature,
                max_completion_tokens=self.max_completion_tokens,
            )
            content = response.choices[0].message.content or ""
            return self._parse_entries(content, game_id, game_result)
        except Exception as exc:
            logger.warning("MemoryWriter: extraction failed: %s", exc)
            return []

    @staticmethod
    def _parse_entries(
        content: str,
        game_id: str,
        game_result: str,
    ) -> list[MemoryEntry]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            logger.warning("MemoryWriter: no JSON object found in response")
            return []

        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            logger.warning("MemoryWriter: JSON parse error: %s", exc)
            return []

        entries: list[MemoryEntry] = []
        for item in data.get("entries", []):
            if not isinstance(item, dict):
                continue
            entry_text = str(item.get("text", "")).strip()
            if not entry_text:
                continue
            raw_tags = item.get("tags", {})
            tags = {k: str(v) for k, v in raw_tags.items() if isinstance(k, str)}
            entries.append(
                MemoryEntry(
                    text=entry_text,
                    tags=tags,
                    source_game_id=game_id,
                    game_result=game_result,
                )
            )
        logger.info("MemoryWriter: extracted %d entries", len(entries))
        return entries
