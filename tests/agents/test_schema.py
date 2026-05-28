from ptcgbench.agents.interfaces.schema import (
    AbilityInfo,
    AttackInfo,
    CardObservation,
    PlayerObservation,
    PokemonObservation,
    StateObservation,
)


def test_attack_info_fields():
    a = AttackInfo(name="Burning Darkness", damage=100, cost=["FIRE", "COLORLESS"], text="")
    assert a.name == "Burning Darkness"
    assert a.damage == 100
    assert a.cost == ["FIRE", "COLORLESS"]


def test_ability_info_fields():
    a = AbilityInfo(name="Starbirth", ability_type="ACTIVE_ABILITY", text="Search deck.")
    assert a.ability_type == "ACTIVE_ABILITY"


def test_pokemon_observation_fields():
    p = PokemonObservation(
        id="PAF-001",
        name="Charizard ex",
        hp=330,
        damage_counters=3,
        card_type="FIRE",
        stage="STAGE_2",
        pokemon_type="EX",
        retreat_cost=["COLORLESS", "COLORLESS"],
        energy=["FIRE"],
        tools=[],
        attacks=[AttackInfo(name="Burning Darkness", damage=180, cost=["FIRE", "COLORLESS"])],
        abilities=[],
        prize=2,
    )
    assert p.damage_counters == 3
    assert p.prize == 2


def test_player_observation_fields():
    p = PlayerObservation(
        active=[],
        bench=[],
        hand=[
            CardObservation(id="PAF-001", name="Charizard ex"),
            CardObservation(id="PAF-050", name="Fire Energy"),
        ],
        hand_count=2,
        deck_count=40,
        prize_count=4,
        discard=[CardObservation(id="PAF-030", name="Arven")],
        discard_count=1,
        energy_played=False,
        supporter_played=True,
        retreated=False,
    )
    assert p.hand_count == 2
    assert p.prize_count == 4
    assert p.energy_played is False


def test_state_observation_fields():
    player = PlayerObservation(
        active=[],
        bench=[],
        hand=[],
        hand_count=0,
        deck_count=30,
        prize_count=6,
        discard=[],
        discard_count=0,
        energy_played=False,
        supporter_played=False,
        retreated=False,
    )
    s = StateObservation(
        turn="player1",
        turn_number=1,
        timestep=3,
        my=player,
        opponent=player,
        stadium=None,
        choosing_card=False,
        choosing_tips="",
    )
    assert s.turn == "player1"
    assert s.stadium is None
