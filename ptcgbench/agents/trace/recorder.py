from __future__ import annotations

from ptcgbench.agents.interfaces.schema import StateObservation
from ptcgbench.agents.trace.schema import GameSummary, GameTrace, PokemonSnapshot, TurnRecord


class TraceRecorder:
    """Accumulates per-turn snapshots during a game and finalizes them into a GameTrace.

    Usage::

        recorder = TraceRecorder()
        # ... in predict():
        recorder.record_turn(observation, thought="...", action="attack(Charizard ex, ...)")
        # ... in close():
        trace = recorder.finalize(result="win", my_deck="charizard_ex", opp_deck="gardevoir_ex")
        trace.save(record_dir / "trace.json")
        recorder.reset()
    """

    def __init__(self) -> None:
        self._turns: list[TurnRecord] = []
        self._prev_my_prizes: int | None = None
        self._prev_opp_prizes: int | None = None

    def reset(self) -> None:
        self._turns.clear()
        self._prev_my_prizes = None
        self._prev_opp_prizes = None

    def record_turn(
        self,
        observation: StateObservation,
        thought: str,
        action: str,
    ) -> None:
        my_prizes = observation.my.prize_count
        opp_prizes = observation.opponent.prize_count

        my_scored = self._prev_my_prizes is not None and my_prizes < self._prev_my_prizes
        opp_scored = self._prev_opp_prizes is not None and opp_prizes < self._prev_opp_prizes

        my_active = (
            self._pokemon_snapshot(observation.my.active[0]) if observation.my.active else None
        )
        opp_active = (
            self._pokemon_snapshot(observation.opponent.active[0])
            if observation.opponent.active
            else None
        )

        self._turns.append(
            TurnRecord(
                turn_number=observation.turn_number,
                timestep=observation.timestep,
                my_prizes=my_prizes,
                opp_prizes=opp_prizes,
                my_active=my_active,
                opp_active=opp_active,
                available_actions=list(observation.available_actions),
                thought=thought,
                action=action,
                my_scored=my_scored,
                opp_scored=opp_scored,
            )
        )

        self._prev_my_prizes = my_prizes
        self._prev_opp_prizes = opp_prizes

    def finalize(
        self,
        result: str = "unknown",
        my_deck: str = "",
        opp_deck: str = "",
    ) -> GameTrace:
        summary = GameSummary(
            result=result,
            total_turns=len(self._turns),
            my_deck=my_deck,
            opp_deck=opp_deck,
            my_prize_progression=[t.my_prizes for t in self._turns],
            opp_prize_progression=[t.opp_prizes for t in self._turns],
            inflection_indices=[i for i, t in enumerate(self._turns) if t.opp_scored],
        )
        return GameTrace(turns=list(self._turns), summary=summary)

    @staticmethod
    def _pokemon_snapshot(obs: object) -> PokemonSnapshot:
        hp = getattr(obs, "hp", 0)
        damage_counters = getattr(obs, "damage_counters", 0)
        return PokemonSnapshot(
            name=getattr(obs, "name", ""),
            current_hp=hp - damage_counters * 10,
            max_hp=hp,
            energy=list(getattr(obs, "energy", [])),
        )
