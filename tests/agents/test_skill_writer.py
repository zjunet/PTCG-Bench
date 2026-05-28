"""Tests for SkillWriter — creation, validation, and tool-based agent loop."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from ptcgbench.agents.skills.skill_writer import (
    SkillWriter,
    _has_insight_data,
    _validate_frontmatter,
)

# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

_VALID_SKILL_MD = """\
---
name: charizard-ex-aggression
description: Play the Charizard ex aggression deck. Use when playing the charizard_ex deck or mentions Charizard ex.
---

# Charizard ex Aggression

## Archetype: Direct Aggression

Hulk smash!

## Quick Start

1. Attack for KO
2. Evolve into Charizard ex
"""

_SKILL_NO_NAME = """\
---
description: A skill without a name.
---

# Some Skill

Body text.
"""

_SKILL_NO_DESCRIPTION = """\
---
name: no-desc-skill
---

# No Desc

Body.
"""

_SKILL_NO_FRONTMATTER = "Just markdown, no frontmatter at all."

_SKILL_BAD_YAML = """\
---
name: [invalid: yaml
---

Body.
"""

_SAMPLE_REFLECTION = {
    "summary": "Game against random deck.",
    "lessons": [
        {
            "title": "Prioritize evolution",
            "category": "strategy",
            "importance": "high",
            "lesson": "Evolve Charmander to Charizard ex as early as turn 2.",
            "phase": "opening",
            "card_names": ["Charizard ex", "Rare Candy"],
            "action_types": ["evolve_pokemon"],
            "situation": ["setup"],
            "confidence": 0.9,
            "evidence": ["Used Rare Candy on turn 2."],
        }
    ],
    "heuristics": [
        {
            "heuristic": "Always use Pidgeot ex Quick Search before ending turn.",
            "card_names": ["Pidgeot ex"],
            "action_types": ["use_ability"],
            "situation": [],
            "confidence": 0.8,
        }
    ],
}

_SAMPLE_BATTLE_SUMMARY = {
    "agent_name": "llm_deepseek-chat",
    "opponent_name": "random",
    "my_deck": "charizard_ex",
    "opponent_deck": "default",
    "result": "win",
    "turn_count": 12,
}

_EMPTY_REFLECTION = {
    "summary": "No useful data.",
    "lessons": [],
    "heuristics": [],
}

_EXISTING_SKILL_MD = """\
---
name: charizard-ex-aggression
description: Play the Charizard ex aggression deck. Use when playing the charizard_ex deck or mentions Charizard ex.
---

# Charizard ex Aggression

## Quick Start

1. Attack for KO
2. Evolve into Charizard ex
"""

_MERGED_SKILL_MD = """\
---
name: charizard-ex-aggression
description: Play the Charizard ex aggression deck. Use when playing the charizard_ex deck or mentions Charizard ex.
---

# Charizard ex Aggression

## Quick Start

1. Attack for KO
2. Evolve into Charizard ex
3. Use Pidgeot ex Quick Search before ending turn

## Key Insight

Always use supporter before attaching energy.
"""


# ---------------------------------------------------------------------------
# Mock helpers for the tool-calling agent loop
# ---------------------------------------------------------------------------


def _make_tool_call(call_id: str, name: str, args: dict) -> MagicMock:
    """Create a mock tool_call object."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _make_message(
    tool_calls: list[MagicMock] | None = None, content: str | None = None
) -> MagicMock:
    """Create a mock message object from a ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    msg.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in tool_calls
        ]
        if tool_calls
        else None,
    }
    return msg


def _make_response(message: MagicMock) -> MagicMock:
    """Create a mock ChatCompletion response."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = message
    return resp


def _mock_create_skill_client(skill_content: str) -> MagicMock:
    """Mock client where LLM calls list_skills then create_skill in one turn."""
    list_tc = _make_tool_call("call_1", "list_skills", {})
    create_tc = _make_tool_call("call_2", "create_skill", {"content": skill_content})
    msg = _make_message(tool_calls=[list_tc, create_tc])
    resp = _make_response(msg)

    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


def _mock_refine_skill_client(name: str, content: str) -> MagicMock:
    """Mock client where LLM calls list_skills, read_skill, then refine_skill."""
    list_tc = _make_tool_call("call_1", "list_skills", {})
    read_tc = _make_tool_call("call_2", "read_skill", {"name": name})
    refine_tc = _make_tool_call("call_3", "refine_skill", {"name": name, "content": content})
    msg = _make_message(tool_calls=[list_tc, read_tc, refine_tc])
    resp = _make_response(msg)

    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


def _mock_client_no_tool_calls() -> MagicMock:
    """Mock client where LLM returns a plain text response (no tool calls)."""
    msg = _make_message(content="I don't have enough information to create a skill.")
    resp = _make_response(msg)

    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


def _write_existing_skill(skills_dir: Path, content: str = _EXISTING_SKILL_MD) -> Path:
    """Create an existing skill in skills_dir and return its SKILL.md path."""
    skill_dir = skills_dir / "charizard-ex-aggression"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8")
    return skill_md


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidateFrontmatter:
    def test_valid_skill(self) -> None:
        valid, error = _validate_frontmatter(_VALID_SKILL_MD)
        assert valid is True
        assert error == ""

    def test_missing_name(self) -> None:
        valid, error = _validate_frontmatter(_SKILL_NO_NAME)
        assert valid is False
        assert "name" in error

    def test_missing_description(self) -> None:
        valid, error = _validate_frontmatter(_SKILL_NO_DESCRIPTION)
        assert valid is False
        assert "description" in error

    def test_no_frontmatter(self) -> None:
        valid, error = _validate_frontmatter(_SKILL_NO_FRONTMATTER)
        assert valid is False

    def test_bad_yaml(self) -> None:
        valid, error = _validate_frontmatter(_SKILL_BAD_YAML)
        assert valid is False


class TestHasInsightData:
    def test_with_lessons(self) -> None:
        assert _has_insight_data(_SAMPLE_REFLECTION) is True

    def test_empty_reflection(self) -> None:
        assert _has_insight_data(_EMPTY_REFLECTION) is False

    def test_only_heuristics(self) -> None:
        reflection = {"lessons": [], "heuristics": [{"heuristic": "rule"}]}
        assert _has_insight_data(reflection) is True

    def test_missing_keys(self) -> None:
        assert _has_insight_data({}) is False


# ---------------------------------------------------------------------------
# SkillWriter.write() tests
# ---------------------------------------------------------------------------


class TestSkillWriterCreate:
    def test_creates_skill_file(self, tmp_path: Path) -> None:
        client = _mock_create_skill_client(_VALID_SKILL_MD)
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=client)
        result = writer.write(_SAMPLE_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        assert result is not None
        assert result.name == "SKILL.md"
        assert result.parent.name == "charizard-ex-aggression"
        assert result.read_text(encoding="utf-8").strip() == _VALID_SKILL_MD.strip()

    def test_creates_skills_dir_if_missing(self, tmp_path: Path) -> None:
        client = _mock_create_skill_client(_VALID_SKILL_MD)
        skills_dir = tmp_path / "new_skills"

        writer = SkillWriter(skills_dir=skills_dir, client=client)
        result = writer.write(_SAMPLE_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        assert result is not None
        assert skills_dir.is_dir()

    def test_skips_empty_reflection(self, tmp_path: Path) -> None:
        client = MagicMock()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=client)
        result = writer.write(_EMPTY_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        assert result is None
        client.chat.completions.create.assert_not_called()

    def test_skips_when_no_skills_dir(self) -> None:
        client = MagicMock()

        writer = SkillWriter(skills_dir=None, client=client)
        result = writer.write(_SAMPLE_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        assert result is None

    def test_returns_none_on_llm_error(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API error")

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=client)
        result = writer.write(_SAMPLE_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        assert result is None

    def test_returns_none_when_no_tool_calls(self, tmp_path: Path) -> None:
        """LLM returns plain text with no tool calls — no skill written."""
        client = _mock_client_no_tool_calls()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=client)
        result = writer.write(_SAMPLE_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        assert result is None

    def test_skill_is_discoverable_by_registry(self, tmp_path: Path) -> None:
        """Verify generated skill works with SkillRegistry."""
        from ptcgbench.agents.skills.skill_registry import SkillRegistry

        client = _mock_create_skill_client(_VALID_SKILL_MD)
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=client)
        writer.write(_SAMPLE_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        registry = SkillRegistry(skills_dir)
        assert "charizard-ex-aggression" in registry.skill_names()
        skill = registry.get("charizard-ex-aggression")
        assert skill is not None
        assert "Charizard ex" in skill.description


# ---------------------------------------------------------------------------
# Tool dispatch tests
# ---------------------------------------------------------------------------


class TestToolDispatch:
    def test_list_skills_returns_catalog(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_existing_skill(skills_dir)

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        result = writer._tool_list_skills()

        catalog = json.loads(result)
        assert len(catalog) == 1
        assert catalog[0]["name"] == "charizard-ex-aggression"

    def test_list_skills_empty_dir(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        result = writer._tool_list_skills()

        assert result == "[]"

    def test_read_skill_returns_content(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_existing_skill(skills_dir)

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        result = writer._tool_read_skill("charizard-ex-aggression")
        assert "Charizard ex Aggression" in result

    def test_read_skill_not_found(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        result = writer._tool_read_skill("nonexistent")
        assert "not found" in result

    def test_create_skill_writes_file(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        msg, path = writer._tool_create_skill(_VALID_SKILL_MD)

        assert path is not None
        assert path.exists()
        assert "Skill created" in msg

    def test_create_skill_rejects_invalid_frontmatter(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        msg, path = writer._tool_create_skill(_SKILL_NO_DESCRIPTION)

        assert path is None
        assert "invalid frontmatter" in msg

    def test_refine_skill_updates_existing(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        existing = _write_existing_skill(skills_dir)

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        msg, path = writer._tool_refine_skill("charizard-ex-aggression", _MERGED_SKILL_MD)

        assert path == existing
        content = path.read_text(encoding="utf-8")
        assert "Pidgeot ex Quick Search" in content

    def test_refine_skill_not_found(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        msg, path = writer._tool_refine_skill("nonexistent", _VALID_SKILL_MD)

        assert path is None
        assert "not found" in msg

    def test_execute_tool_handles_bad_json(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        tc = MagicMock()
        tc.function.name = "read_skill"
        tc.function.arguments = "not valid json {{{"

        msg, path = writer._execute_tool(tc)
        assert path is None
        assert "invalid JSON" in msg

    def test_execute_tool_handles_unknown_tool(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        tc = _make_tool_call("call_x", "unknown_tool", {})

        msg, path = writer._execute_tool(tc)
        assert path is None
        assert "unknown tool" in msg


# ---------------------------------------------------------------------------
# Agent loop tests
# ---------------------------------------------------------------------------


class TestAgentLoop:
    def test_multi_turn_create(self, tmp_path: Path) -> None:
        """LLM calls list_skills (turn 1), then create_skill (turn 2)."""
        # Turn 1: list_skills only
        tc1 = _make_tool_call("call_1", "list_skills", {})
        msg1 = _make_message(tool_calls=[tc1])
        resp1 = _make_response(msg1)

        # Turn 2: create_skill
        tc2 = _make_tool_call("call_2", "create_skill", {"content": _VALID_SKILL_MD})
        msg2 = _make_message(tool_calls=[tc2])
        resp2 = _make_response(msg2)

        client = MagicMock()
        client.chat.completions.create.side_effect = [resp1, resp2]

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=client)
        result = writer.write(_SAMPLE_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        assert result is not None
        assert result.parent.name == "charizard-ex-aggression"
        assert client.chat.completions.create.call_count == 2

    def test_refine_existing_skill(self, tmp_path: Path) -> None:
        """LLM discovers existing skill, reads it, then refines it."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        existing_path = _write_existing_skill(skills_dir)

        client = _mock_refine_skill_client("charizard-ex-aggression", _MERGED_SKILL_MD)
        writer = SkillWriter(skills_dir=skills_dir, client=client)
        result = writer.write(_SAMPLE_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        assert result == existing_path
        content = result.read_text(encoding="utf-8")
        assert "Pidgeot ex Quick Search" in content
        assert "supporter before attaching energy" in content

    def test_invalid_create_rejected_no_file_written(self, tmp_path: Path) -> None:
        """LLM calls create_skill with invalid frontmatter — tool returns error, no file."""
        tc = _make_tool_call("call_1", "create_skill", {"content": _SKILL_NO_DESCRIPTION})
        msg = _make_message(tool_calls=[tc])
        resp = _make_response(msg)

        # Second turn: LLM gives up (no tool calls)
        msg2 = _make_message(content="Cannot create skill")
        resp2 = _make_response(msg2)

        client = MagicMock()
        client.chat.completions.create.side_effect = [resp, resp2]

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=client)
        result = writer.write(_SAMPLE_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        assert result is None

    def test_max_turns_exhausted(self, tmp_path: Path) -> None:
        """Agent loop respects _MAX_TURNS and returns None if no skill written."""
        # Keep returning tool calls that don't write anything
        tc = _make_tool_call("call_1", "list_skills", {})
        msg = _make_message(tool_calls=[tc])
        resp = _make_response(msg)

        client = MagicMock()
        client.chat.completions.create.return_value = resp

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=client)
        result = writer.write(_SAMPLE_REFLECTION, _SAMPLE_BATTLE_SUMMARY)

        assert result is None


# ---------------------------------------------------------------------------
# Find / write helpers
# ---------------------------------------------------------------------------


class TestFindSkillPath:
    def test_finds_existing_skill(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_existing_skill(skills_dir)

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        path = writer._find_skill_path("charizard-ex-aggression")
        assert path is not None
        assert path.parent.name == "charizard-ex-aggression"

    def test_returns_none_for_unknown(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        assert writer._find_skill_path("nonexistent") is None

    def test_returns_none_when_no_skills_dir(self) -> None:
        writer = SkillWriter(skills_dir=None, client=MagicMock())
        assert writer._find_skill_path("anything") is None


class TestWriteNewSkill:
    def test_creates_directory_and_file(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        path = writer._write_new_skill(_VALID_SKILL_MD)

        assert path.exists()
        assert path.parent.name == "charizard-ex-aggression"

    def test_directory_name_from_frontmatter(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        writer = SkillWriter(skills_dir=skills_dir, client=MagicMock())
        path = writer._write_new_skill(_VALID_SKILL_MD)

        assert path.parent.name == "charizard-ex-aggression"


# ---------------------------------------------------------------------------
# Pipeline integration tests
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    @staticmethod
    def _make_reflection_agent(tmp_path: Path, skill_writer: SkillWriter | None):
        """Create a ReflectionAgent with mocked internals for testing."""
        from unittest.mock import MagicMock

        from ptcgbench.agents.memory.reflection_agent import ReflectionAgent

        mock_openai = MagicMock()
        agent = ReflectionAgent(
            skill_writer=skill_writer,
            knowledge_base_file=str(tmp_path / "kb.json"),
            client=mock_openai,
        )
        # Stub internal methods to avoid file I/O and LLM calls
        agent._load_from_file = lambda path: [{"role": "assistant", "content": "test"}]  # type: ignore
        agent.summary_agent.compress = lambda history, max_turns: "stubbed turn summary"  # type: ignore
        agent._generate_reflection = lambda prompt: _SAMPLE_REFLECTION  # type: ignore
        return agent

    def test_reflection_agent_accepts_skill_writer(self, tmp_path: Path) -> None:
        """ReflectionAgent accepts optional skill_writer without error."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        llm_client = _mock_create_skill_client(_VALID_SKILL_MD)
        writer = SkillWriter(skills_dir=skills_dir, client=llm_client)
        agent = self._make_reflection_agent(tmp_path, writer)
        assert agent.skill_writer is writer

    def test_reflection_agent_works_without_skill_writer(self, tmp_path: Path) -> None:
        """ReflectionAgent works fine with skill_writer=None (default)."""
        agent = self._make_reflection_agent(tmp_path, None)
        assert agent.skill_writer is None

    def test_reflect_then_write_chains(self, tmp_path: Path) -> None:
        """reflect() + skill_writer.write() produces a skill file."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        llm_client = _mock_create_skill_client(_VALID_SKILL_MD)
        writer = SkillWriter(skills_dir=skills_dir, client=llm_client)
        agent = self._make_reflection_agent(tmp_path, writer)

        result = agent.reflect(tmp_path / "history.jsonl")

        skill_path = writer.write(result, _SAMPLE_BATTLE_SUMMARY)
        assert skill_path is not None
        assert skill_path.exists()
        assert "charizard-ex-aggression" in skill_path.read_text(encoding="utf-8")

    def test_reflect_without_skill_writer(self, tmp_path: Path) -> None:
        """reflect() works fine with skill_writer=None."""
        agent = self._make_reflection_agent(tmp_path, None)

        result = agent.reflect(tmp_path / "history.jsonl")

        assert "skill_path" not in result

    def test_end_to_end_skill_discoverable(self, tmp_path: Path) -> None:
        """Full pipeline: reflect -> write skill -> SkillRegistry finds it."""
        from ptcgbench.agents.skills.skill_registry import SkillRegistry

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        llm_client = _mock_create_skill_client(_VALID_SKILL_MD)
        writer = SkillWriter(skills_dir=skills_dir, client=llm_client)
        agent = self._make_reflection_agent(tmp_path, writer)

        result = agent.reflect(tmp_path / "history.jsonl")
        skill_path = writer.write(result, _SAMPLE_BATTLE_SUMMARY)
        assert skill_path is not None

        # Verify SkillRegistry can discover the skill
        registry = SkillRegistry(skills_dir)
        assert "charizard-ex-aggression" in registry.skill_names()
        catalog = registry.build_catalog()
        assert "charizard-ex-aggression" in catalog
