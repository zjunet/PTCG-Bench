import pytest

from ptcgbench.agents.interfaces.observer import StateObserver
from ptcgbench.agents.interfaces.schema import StateObservation
from ptcg.core.envs import PokemonTCG


@pytest.fixture
def game_state():
    """返回一个已初始化好的 (obs, info) 元组。"""
    env = PokemonTCG(seed=42, record_game=False)
    obs, reward, done, info = env.reset()
    return obs, info


def test_observe_returns_state_observation(game_state):
    obs, info = game_state
    observer = StateObserver()
    result = observer.observe(obs, info)
    assert isinstance(result, StateObservation)


def test_observe_turn_matches(game_state):
    obs, info = game_state
    observer = StateObserver()
    result = observer.observe(obs, info)
    expected_turn = obs.turn.name.lower()  # "player1" or "player2"
    assert result.turn == expected_turn


def test_my_hand_revealed(game_state):
    """当前行动方的手牌应暴露完整卡名列表。"""
    obs, info = game_state
    observer = StateObserver()
    result = observer.observe(obs, info)
    assert len(result.my.hand) == result.my.hand_count
    assert all(hasattr(c, "id") and hasattr(c, "name") for c in result.my.hand)


def test_opponent_hand_hidden(game_state):
    """对手手牌列表应为空，但 hand_count > 0。"""
    obs, info = game_state
    observer = StateObserver()
    result = observer.observe(obs, info)
    assert result.opponent.hand == []
    assert result.opponent.hand_count == 7


def test_observe_prize_counts(game_state):
    """双方初始奖励牌数均为 6。"""
    obs, info = game_state
    observer = StateObserver()
    result = observer.observe(obs, info)
    assert result.my.prize_count == 6
    assert result.opponent.prize_count == 6


def test_observe_no_stadium_initially(game_state):
    """游戏开始时没有场地卡。"""
    obs, info = game_state
    observer = StateObserver()
    result = observer.observe(obs, info)
    assert result.stadium is None


def test_observe_serializable(game_state):
    """StateObservation 可以序列化为 JSON。"""
    obs, info = game_state
    observer = StateObserver()
    result = observer.observe(obs, info)
    json_str = result.model_dump_json(indent=2)
    assert isinstance(json_str, str)
    assert "turn" in json_str
    assert "my" in json_str


def _advance_past_setup(env, obs, info):
    """Helper: step through ChooseCard phase until normal game state."""
    steps = 0
    while info.get("is_choosing_card") and steps < 20:
        actions = info.get("raw_available_actions", [])
        if not actions:
            break
        obs, _reward, done, info = env.step(actions[0])
        steps += 1
        if done:
            break
    return obs, info


def test_choosing_card_flag(game_state):
    """info["is_choosing_card"] が反映される。"""
    obs, info = game_state
    observer = StateObserver()

    # リセット直後は初期配置フェーズで is_choosing_card=True
    result = observer.observe(obs, info)
    assert result.choosing_card == info.get("is_choosing_card", False)
    assert result.choosing_tips != ""  # 選択中はヒントが入る

    # is_choosing_card=False の場合、choosing_tips は空
    modified_info = dict(info)
    modified_info["is_choosing_card"] = False
    result2 = observer.observe(obs, modified_info)
    assert result2.choosing_card is False
    assert result2.choosing_tips == ""


def test_active_pokemon_obs_fields():
    """アクティブポケモンの PokemonObservation フィールドが正しくマッピングされる。"""
    from ptcg.core.envs import PokemonTCG

    env = PokemonTCG(seed=42, record_game=False)
    obs, _reward, _done, info = env.reset()
    # セットアップフェーズを終了してアクティブポケモンが配置された状態に進む
    obs, info = _advance_past_setup(env, obs, info)

    observer = StateObserver()
    result = observer.observe(obs, info)
    # 両プレイヤーは初期化時にアクティブポケモンを選択している
    assert len(result.my.active) == 1
    poke = result.my.active[0]
    assert isinstance(poke.name, str) and poke.name != ""
    assert poke.hp > 0
    assert poke.damage_counters == 0  # 初期状態では無傷
    assert isinstance(poke.prize, int)
    assert isinstance(poke.attacks, list)
    assert isinstance(poke.abilities, list)
    assert isinstance(poke.energy, list)
    assert isinstance(poke.tools, list)
