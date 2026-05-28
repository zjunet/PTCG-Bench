"""Verify SkillEvolvingAgent wiring without calling the real LLM API."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ptcgbench.agents.common.profile import AgentProfile
from ptcgbench.agents.interfaces.executor import ToolCallExecutor
from ptcgbench.agents.interfaces.observer import StateObserver
from ptcgbench.agents.interfaces.schema import StateObservation
from ptcgbench.agents.skill_evolving_agent import SkillEvolvingAgent
from ptcg.core.action import ChooseCardAction
from ptcg.core.envs import PokemonTCG


@pytest.fixture
def game_info():
    env = PokemonTCG(seed=42, record_game=False)
    obs, reward, done, info = env.reset()
    return obs, info


def test_build_user_message_returns_encoded_observation(game_info):
    """_build_user_message should serialize the observed state."""
    obs, info = game_info
    agent = SkillEvolvingAgent.__new__(SkillEvolvingAgent)
    agent.model = "test"
    agent.observer = StateObserver()
    agent.executor = ToolCallExecutor()
    agent._history = []

    observation = agent.observer.observe(obs, info)
    message = agent._build_user_message(observation)
    assert isinstance(message, str)
    assert message


def test_observer_and_executor_wired(game_info):
    """observer produces StateObservation, executor consumes tool calls — types align."""
    obs, info = game_info
    observer = StateObserver()
    executor = ToolCallExecutor()

    state_obs = observer.observe(obs, info)
    assert isinstance(state_obs, StateObservation)

    choose_actions = [a for a in info["raw_available_actions"] if isinstance(a, ChooseCardAction)]
    assert choose_actions, "Expected CHOOSE_CARD_ACTION actions at game reset"

    target = choose_actions[0]
    chosen_card_names = [c.name for c in target.chosen]
    result = executor.execute(
        "choose_card",
        {"chosen_cards": chosen_card_names},
        info,
    )
    assert result.level == "FULL"
    assert result.action in info["raw_available_actions"]
    assert isinstance(result.action, ChooseCardAction)


def test_notify_game_start_and_close(tmp_path: Path):
    """Integration test: notify_game_start creates battle record, close writes all files."""
    with patch.object(SkillEvolvingAgent, "__init__", lambda self, **kw: None):
        agent = SkillEvolvingAgent.__new__(SkillEvolvingAgent)
        agent.name = "llm_deepseek-chat"
        agent.profile = AgentProfile(name="llm_deepseek-chat", root=tmp_path)
        agent.profile.ensure_dirs()
        agent._turn_count = 0
        agent._battle_record = None
        agent._system_prompt = "test system prompt"

        from ptcgbench.agents.memory.context_manager import ContextManager

        agent.context_manager = ContextManager(
            model="deepseek-chat",
            system_prompt=agent._system_prompt,
            max_tokens=80000,
        )
        agent.tool_dispatcher = MagicMock()
        agent.reflection_agent = None

    # Start game
    agent.notify_game_start(
        my_deck="charizard-ex",
        opponent_deck="gardevoir-ex",
        opponent_name="random",
    )

    # Simulate some messages
    agent.context_manager.add_message({"role": "user", "content": "test message"})

    # Close game
    agent.close(result="win", my_prizes=3, opponent_prizes=0)

    # Verify battle record files exist
    battles_dir = agent.profile.battles_dir
    battle_dirs = list(battles_dir.iterdir())
    assert len(battle_dirs) == 1

    battle_dir = battle_dirs[0]
    assert (battle_dir / "conversation.jsonl").exists()
    assert (battle_dir / "summary.json").exists()

    # Verify summary content
    summary = json.loads((battle_dir / "summary.json").read_text())
    assert summary["result"] == "win"
    assert summary["agent_name"] == "llm_deepseek-chat"
    assert summary["opponent_name"] == "random"
    assert summary["my_deck"] == "charizard-ex"
    assert summary["opponent_deck"] == "gardevoir-ex"
    assert summary["my_prizes_remaining"] == 3
    assert summary["opponent_prizes_remaining"] == 0

    # Verify conversation has messages (system + user)
    conv_lines = (battle_dir / "conversation.jsonl").read_text().strip().splitlines()
    assert len(conv_lines) >= 2  # system prompt + user message


def test_notify_game_start_includes_deck_composition_in_system_prompt(tmp_path: Path):
    with patch.object(SkillEvolvingAgent, "__init__", lambda self, **kw: None):
        agent = SkillEvolvingAgent.__new__(SkillEvolvingAgent)
        agent.name = "llm_deepseek-chat"
        agent.profile = AgentProfile(name="llm_deepseek-chat", root=tmp_path)
        agent.profile.ensure_dirs()
        agent._turn_count = 0
        agent._battle_record = None
        agent._system_prompt = "test system prompt"

        from ptcgbench.agents.memory.context_manager import ContextManager

        agent.context_manager = ContextManager(
            model="deepseek-chat",
            system_prompt=agent._system_prompt,
            max_tokens=80000,
        )
        agent.tool_dispatcher = MagicMock()
        agent.reflection_agent = None

    agent.notify_game_start(
        my_deck="charizard-ex",
        opponent_deck="charizard-ex",
        opponent_name="mirror",
    )

    assert "Deck Composition" in agent._system_prompt
    assert "Pokémon: 20" in agent._system_prompt
    assert "4 Charmander PAF 7" in agent._system_prompt
    assert "7 Basic {R} Energy SVE 2" in agent._system_prompt
    assert "Opponent deck composition" not in agent._system_prompt
    assert "The opponent's full decklist is hidden information." in agent._system_prompt


def test_evolve_uses_battles_dir_without_active_battle_record(tmp_path: Path):
    """evolve() should reflect over the battles directory even without a live battle record."""
    with patch.object(SkillEvolvingAgent, "__init__", lambda self, **kw: None):
        agent = SkillEvolvingAgent.__new__(SkillEvolvingAgent)
        agent.name = "llm_deepseek-chat"
        agent.profile = AgentProfile(name="llm_deepseek-chat", root=tmp_path)
        agent.profile.ensure_dirs()
        agent._battle_record = None
        agent._skill_writer = None
        agent.reflection_agent = MagicMock()
        agent.reflection_agent.reflect.return_value = {"lessons": [], "heuristics": []}

    battle_dir = agent.profile.battles_dir / "2026-01-01_test"
    battle_dir.mkdir(parents=True)
    (battle_dir / "conversation.jsonl").write_text(
        '{"role":"user","content":"x"}\n', encoding="utf-8"
    )

    reflection = agent.evolve({"my_deck": "charizard_ex"})

    assert reflection == {"lessons": [], "heuristics": []}
    agent.reflection_agent.reflect.assert_called_once_with(agent.profile.battles_dir)


def test_evolve_prefers_active_battle_record(tmp_path: Path):
    """evolve() should reflect only the current battle when a live battle record exists."""
    with patch.object(SkillEvolvingAgent, "__init__", lambda self, **kw: None):
        agent = SkillEvolvingAgent.__new__(SkillEvolvingAgent)
        agent.name = "llm_deepseek-chat"
        agent.profile = AgentProfile(name="llm_deepseek-chat", root=tmp_path)
        agent.profile.ensure_dirs()
        agent._skill_writer = None
        agent.reflection_agent = MagicMock()
        agent.reflection_agent.reflect.return_value = {"lessons": [], "heuristics": []}

    battle_dir = agent.profile.battles_dir / "2026-01-01_test"
    battle_dir.mkdir(parents=True)
    (battle_dir / "conversation.jsonl").write_text(
        '{"role":"user","content":"x"}\n', encoding="utf-8"
    )

    agent._battle_record = MagicMock()
    agent._battle_record.record_dir = battle_dir

    reflection = agent.evolve({"my_deck": "charizard_ex"})

    assert reflection == {"lessons": [], "heuristics": []}
    agent.reflection_agent.reflect.assert_called_once_with(battle_dir)


def test_evolve_respects_explicit_history_path(tmp_path: Path):
    """evolve() should use an explicit history_path instead of inferred defaults."""
    with patch.object(SkillEvolvingAgent, "__init__", lambda self, **kw: None):
        agent = SkillEvolvingAgent.__new__(SkillEvolvingAgent)
        agent.name = "llm_deepseek-chat"
        agent.profile = AgentProfile(name="llm_deepseek-chat", root=tmp_path)
        agent.profile.ensure_dirs()
        agent._skill_writer = None
        agent.reflection_agent = MagicMock()
        agent.reflection_agent.reflect.return_value = {"lessons": [], "heuristics": []}

    active_battle_dir = agent.profile.battles_dir / "active"
    active_battle_dir.mkdir(parents=True)
    (active_battle_dir / "conversation.jsonl").write_text(
        '{"role":"user","content":"x"}\n', encoding="utf-8"
    )

    explicit_dir = tmp_path / "batch_history"
    explicit_dir.mkdir(parents=True)
    (explicit_dir / "conversation.jsonl").write_text(
        '{"role":"user","content":"y"}\n', encoding="utf-8"
    )

    agent._battle_record = MagicMock()
    agent._battle_record.record_dir = active_battle_dir

    reflection = agent.evolve({"my_deck": "charizard_ex"}, history_path=explicit_dir)

    assert reflection == {"lessons": [], "heuristics": []}
    agent.reflection_agent.reflect.assert_called_once_with(explicit_dir)
