import pytest

from ptcgbench.agents.interfaces.executor import ToolCallExecutor
from ptcg.core.action import PassTurn
from ptcg.core.envs import PokemonTCG


@pytest.fixture
def game_info():
    env = PokemonTCG(seed=42, record_game=False)
    obs, reward, done, info = env.reset()
    while not done and not any(isinstance(a, PassTurn) for a in info["raw_available_actions"]):
        obs, reward, done, info = env.step(info["raw_available_actions"][0])
    return obs, info


def test_execute_pass_turn(game_info):
    """PASS_TURN 应能匹配到合法 action。"""
    obs, info = game_info
    executor = ToolCallExecutor()
    result = executor.execute("pass_turn", {}, info)
    assert result.level == "FULL"
    assert result.action in info["raw_available_actions"]
    assert isinstance(result.action, PassTurn)


def test_execute_fallback_on_unknown(game_info):
    """无法匹配时应返回 NONE 级别。"""
    obs, info = game_info
    executor = ToolCallExecutor()
    result = executor.execute(
        "attack",
        {"source_card": "NonExistentCard", "attack_name": "Unknown Attack"},
        info,
    )
    assert result.level in ("NONE", "TYPE_ONLY", "PARTIAL")
    assert result.action is None


def test_execute_returns_valid_action(game_info):
    """任何输出都应返回 raw_available_actions 中的合法 action（当匹配成功时）。"""
    obs, info = game_info
    executor = ToolCallExecutor()
    first_action = info["raw_available_actions"][0]
    result = executor.execute(
        "pass_turn",
        {},
        info,
    )
    if result.level == "FULL":
        assert result.action in info["raw_available_actions"]


def test_execute_play_pokemon_bench(game_info):
    """PLAY_POKEMON_ACTION with position=BENCH should match the correct action."""
    obs, info = game_info
    executor = ToolCallExecutor()

    from ptcg.core.action import PlayPokemonAction
    from ptcg.core.enums import PokemonPosition

    bench_actions = [
        a
        for a in info["raw_available_actions"]
        if isinstance(a, PlayPokemonAction) and a.position == PokemonPosition.BENCH
    ]

    if not bench_actions:
        pytest.skip("No PLAY_POKEMON_ACTION for BENCH available in this game state")

    target = bench_actions[0]
    result = executor.execute(
        "play_pokemon",
        {"source_card": target.source.name, "position": "BENCH"},
        info,
    )
    assert result.level == "FULL"
    assert isinstance(result.action, PlayPokemonAction)
    assert result.action in info["raw_available_actions"]
