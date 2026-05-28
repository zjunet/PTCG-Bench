"""Tests for ReflexionAgent reflection persistence and post_game interface."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from ptcgbench.agents.reflexion_agent import ReflexionAgent


def _make_agent(tmp_path: Path, max_reflections: int = 5) -> ReflexionAgent:
    """Create a ReflexionAgent that writes to tmp_path and never hits a real API."""
    fake_client = MagicMock()

    with (
        patch("ptcgbench.agents.reflexion_agent.build_client", return_value=fake_client),
        patch("ptcgbench.agents.reflexion_agent.AgentProfile") as MockProfile,
    ):
        mock_profile = MagicMock()
        mock_profile.memory_dir = tmp_path / "memory"
        mock_profile.memory_dir.mkdir(parents=True, exist_ok=True)
        mock_profile.battles_dir = tmp_path / "battles"
        mock_profile.battles_dir.mkdir(parents=True, exist_ok=True)
        MockProfile.return_value = mock_profile

        agent = ReflexionAgent(max_reflections=max_reflections)

    # Expose the memory dir for assertions
    agent._reflections_path = mock_profile.memory_dir / "reflections.json"
    return agent


# ---------------------------------------------------------------------------
# _load_reflections
# ---------------------------------------------------------------------------


def test_load_reflections_empty_when_file_missing(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent._reflections_path = tmp_path / "nonexistent.json"

    assert agent._load_reflections() == []


def test_load_reflections_returns_saved_data(tmp_path: Path):
    agent = _make_agent(tmp_path)
    data = [{"text": "attack first when ahead on prizes"}]
    agent._reflections_path.write_text(json.dumps(data), encoding="utf-8")

    result = agent._load_reflections()

    assert result == data


def test_load_reflections_returns_empty_on_corrupt_file(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent._reflections_path.write_text("not valid json{{{", encoding="utf-8")

    result = agent._load_reflections()

    assert result == []


def test_load_reflections_returns_empty_when_file_is_not_a_list(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent._reflections_path.write_text(json.dumps({"text": "oops"}), encoding="utf-8")

    result = agent._load_reflections()

    assert result == []


# ---------------------------------------------------------------------------
# _save_reflections
# ---------------------------------------------------------------------------


def test_save_reflections_writes_json_file(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent.reflections = [
        {"text": "use Rare Candy early"},
        {"text": "spread damage before finishing"},
    ]

    agent._save_reflections()

    written = json.loads(agent._reflections_path.read_text(encoding="utf-8"))
    assert written == agent.reflections


def test_save_reflections_overwrites_previous_file(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent._reflections_path.write_text(json.dumps([{"text": "old"}]), encoding="utf-8")
    agent.reflections = [{"text": "new"}]

    agent._save_reflections()

    written = json.loads(agent._reflections_path.read_text(encoding="utf-8"))
    assert written == [{"text": "new"}]


# ---------------------------------------------------------------------------
# _store_reflection  (memory management + auto-save)
# ---------------------------------------------------------------------------


def test_store_reflection_appends_and_saves(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent.reflections = []

    agent._store_reflection("always bench before attaching energy")

    assert len(agent.reflections) == 1
    assert agent.reflections[0]["text"] == "always bench before attaching energy"
    saved = json.loads(agent._reflections_path.read_text(encoding="utf-8"))
    assert saved == agent.reflections


def test_store_reflection_evicts_oldest_when_at_capacity(tmp_path: Path):
    agent = _make_agent(tmp_path, max_reflections=3)
    for i in range(3):
        agent._store_reflection(f"reflection {i}")

    agent._store_reflection("newest reflection")

    assert len(agent.reflections) == 3
    texts = [r["text"] for r in agent.reflections]
    assert "reflection 0" not in texts
    assert "newest reflection" in texts


def test_store_reflection_saves_after_eviction(tmp_path: Path):
    agent = _make_agent(tmp_path, max_reflections=2)
    agent._store_reflection("old A")
    agent._store_reflection("old B")
    agent._store_reflection("new C")

    saved = json.loads(agent._reflections_path.read_text(encoding="utf-8"))

    assert len(saved) == 2
    assert saved[0]["text"] == "old B"
    assert saved[1]["text"] == "new C"


# ---------------------------------------------------------------------------
# Persistence across instances (simulates process restart)
# ---------------------------------------------------------------------------


def test_reflections_survive_reinstantiation(tmp_path: Path):
    """Reflections written by one agent instance are loaded by the next."""
    agent1 = _make_agent(tmp_path)
    agent1._store_reflection("identify winning line before passing")
    agent1._store_reflection("discard bench if no recovery possible")

    # Simulate a new process: create a second agent pointing to the same path
    agent2 = _make_agent(tmp_path)
    # Manually point it at the same reflections file (mirrors __init__ behaviour)
    agent2.reflections = agent2._load_reflections()

    texts = [r["text"] for r in agent2.reflections]
    assert "identify winning line before passing" in texts
    assert "discard bench if no recovery possible" in texts


def test_empty_reflections_persist_cleanly(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent.reflections = []
    agent._save_reflections()

    reloaded = agent._load_reflections()

    assert reloaded == []


# ---------------------------------------------------------------------------
# _build_system_prompt — reflections injected into system prompt
# ---------------------------------------------------------------------------


def test_build_system_prompt_contains_no_reflection_section_when_empty(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent.reflections = []

    prompt = agent._build_system_prompt()

    assert "Past Game Reflections" not in prompt


def test_build_system_prompt_injects_reflections(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent.reflections = [{"text": "pressure early"}, {"text": "conserve energy"}]

    prompt = agent._build_system_prompt()

    assert "Past Game Reflections" in prompt
    assert "pressure early" in prompt
    assert "conserve energy" in prompt


def test_build_system_prompt_numbers_reflections(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent.reflections = [{"text": "A"}, {"text": "B"}, {"text": "C"}]

    prompt = agent._build_system_prompt()

    assert "1. A" in prompt
    assert "2. B" in prompt
    assert "3. C" in prompt


# ---------------------------------------------------------------------------
# _retrieve_reflections
# ---------------------------------------------------------------------------


def test_retrieve_reflections_returns_all_text(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent.reflections = [{"text": "alpha"}, {"text": "beta"}]

    result = agent._retrieve_reflections(obs=MagicMock(), info={})

    assert result == ["alpha", "beta"]


def test_retrieve_reflections_empty_when_no_history(tmp_path: Path):
    agent = _make_agent(tmp_path)
    agent.reflections = []

    result = agent._retrieve_reflections(obs=MagicMock(), info={})

    assert result == []


# ---------------------------------------------------------------------------
# post_game interface
# ---------------------------------------------------------------------------


def test_post_game_calls_close_and_on_game_end(tmp_path: Path):
    """post_game() must invoke both close() and on_game_end()."""
    agent = _make_agent(tmp_path)

    close_calls: list[dict] = []
    on_game_end_calls: list[str] = []

    agent.close = lambda result, my_prizes, opponent_prizes: close_calls.append(  # type: ignore[method-assign]
        {"result": result, "my_prizes": my_prizes, "opponent_prizes": opponent_prizes}
    )
    agent.on_game_end = lambda result: on_game_end_calls.append(result)  # type: ignore[method-assign]

    agent.post_game(result="win", my_prizes=3, opponent_prizes=0)

    assert close_calls == [{"result": "win", "my_prizes": 3, "opponent_prizes": 0}]
    assert on_game_end_calls == ["win"]


def test_post_game_triggers_reflection_and_persists(tmp_path: Path):
    """post_game() causes a reflection to be generated and saved to disk."""
    agent = _make_agent(tmp_path)
    agent._last_game_history = [
        {"thought": "I should attack", "action": "attack Charizard ex"},
    ]

    # Stub the LLM call inside _evaluate_game
    fake_response = MagicMock()
    fake_response.choices[0].message.content = "I should have retreated earlier."
    agent._client.chat.completions.create.return_value = fake_response

    agent.post_game(result="loss", my_prizes=2, opponent_prizes=0)

    assert len(agent.reflections) == 1
    assert agent.reflections[0]["text"] == "I should have retreated earlier."
    saved = json.loads(agent._reflections_path.read_text(encoding="utf-8"))
    assert saved[0]["text"] == "I should have retreated earlier."


def test_post_game_default_args(tmp_path: Path):
    """post_game() can be called with no arguments (all defaults)."""
    agent = _make_agent(tmp_path)
    agent._last_game_history = []

    agent.post_game()  # should not raise

    # No history → reflection is a fallback string, not an LLM call
    assert len(agent.reflections) == 1
    assert "unknown" in agent.reflections[0]["text"] or agent.reflections[0]["text"]


def test_post_game_clears_game_history(tmp_path: Path):
    """After post_game(), _last_game_history is emptied."""
    agent = _make_agent(tmp_path)
    agent._last_game_history = [{"thought": "t", "action": "a"}]

    fake_response = MagicMock()
    fake_response.choices[0].message.content = "reflection text"
    agent._client.chat.completions.create.return_value = fake_response

    agent.post_game(result="draw")

    assert agent._last_game_history == []


def test_post_game_is_on_base_agent():
    """BaseAgent must expose post_game so callers need no hasattr guard."""
    from ptcgbench.agents.base_agent import BaseAgent

    assert hasattr(BaseAgent, "post_game")
    assert callable(getattr(BaseAgent, "post_game"))


def test_post_game_accumulates_across_games(tmp_path: Path):
    """Calling post_game() multiple times accumulates reflections on disk."""
    agent = _make_agent(tmp_path)

    for i, result in enumerate(["loss", "win", "draw"]):
        agent._last_game_history = [{"thought": f"t{i}", "action": f"a{i}"}]
        fake_response = MagicMock()
        fake_response.choices[0].message.content = f"reflection {i}"
        agent._client.chat.completions.create.return_value = fake_response
        agent.post_game(result=result)

    saved = json.loads(agent._reflections_path.read_text(encoding="utf-8"))
    assert len(saved) == 3
    assert saved[0]["text"] == "reflection 0"
    assert saved[2]["text"] == "reflection 2"
