"""Tests for bench.metrics module."""

from pathlib import Path

from ptcgbench.bench.metrics import GameMetrics, MetricsCollector

AGENT_A = "agent_a"
AGENT_B = "agent_b"


def _make_record(
    game_id: int,
    winner_id: str,
    steps: int = 50,
    p1_id: str = AGENT_A,
    p2_id: str = AGENT_B,
) -> GameMetrics:
    return GameMetrics(
        game_id=game_id,
        batch_id=game_id // 5,
        p1_id=p1_id,
        p2_id=p2_id,
        winner_id=winner_id,
        steps=steps,
        timestamp="2026-04-06T00:00:00",
        p1_rating_before=1500.0,
        p1_rating_after=1500.0,
        p2_rating_before=1500.0,
        p2_rating_after=1500.0,
        p1_phi_before=350.0,
        p1_phi_after=340.0,
        p2_phi_before=350.0,
        p2_phi_after=345.0,
    )


class TestMetricsCollector:
    def test_empty_summary(self):
        m = MetricsCollector()
        s = m.summary(agent_ids=[AGENT_A, AGENT_B])
        assert s["total"] == 0

    def test_record_and_summary(self):
        m = MetricsCollector()
        m.record_game(_make_record(0, AGENT_A, steps=30))
        m.record_game(_make_record(1, AGENT_B, steps=60))
        m.record_game(_make_record(2, AGENT_A, steps=40))
        m.record_game(_make_record(3, "draw", steps=50))

        s = m.summary(agent_ids=[AGENT_A, AGENT_B])
        assert s["total"] == 4
        assert s[f"{AGENT_A}_wins"] == 2
        assert s[f"{AGENT_B}_wins"] == 1
        assert s["draws"] == 1
        assert s[f"{AGENT_A}_win_rate"] == 0.5
        assert s["avg_steps"] == 45.0

    def test_rolling_win_rate_all_wins(self):
        m = MetricsCollector()
        for i in range(5):
            m.record_game(_make_record(i, AGENT_A))

        rates = m.rolling_win_rate(window=3, agent_id=AGENT_A)
        assert len(rates) == 5
        for _, rate in rates:
            assert rate == 1.0

    def test_rolling_win_rate_all_losses(self):
        m = MetricsCollector()
        for i in range(5):
            m.record_game(_make_record(i, AGENT_B))

        rates = m.rolling_win_rate(window=3, agent_id=AGENT_A)
        for _, rate in rates:
            assert rate == 0.0

    def test_rolling_win_rate_mixed(self):
        m = MetricsCollector()
        # W W L L W  → window=3
        for w in [AGENT_A, AGENT_A, AGENT_B, AGENT_B, AGENT_A]:
            m.record_game(_make_record(0, w))

        rates = m.rolling_win_rate(window=3, agent_id=AGENT_A)
        # game 0: [W]          → 1/1 = 1.0
        # game 1: [W,W]        → 2/2 = 1.0
        # game 2: [W,W,L]      → 2/3 ≈ 0.667
        # game 3: [W,L,L]      → 1/3 ≈ 0.333
        # game 4: [L,L,W]      → 1/3 ≈ 0.333
        expected = [1.0, 1.0, 2 / 3, 1 / 3, 1 / 3]
        for (_, actual), exp in zip(rates, expected):
            assert abs(actual - exp) < 1e-9

    def test_rolling_win_rate_window_larger_than_count(self):
        m = MetricsCollector()
        m.record_game(_make_record(0, AGENT_A))
        m.record_game(_make_record(1, AGENT_B))

        rates = m.rolling_win_rate(window=100, agent_id=AGENT_A)
        assert len(rates) == 2
        assert rates[0][1] == 1.0  # only 1 game so far
        assert rates[1][1] == 0.5  # 1 win out of 2

    def test_rolling_win_rate_single_game(self):
        m = MetricsCollector()
        m.record_game(_make_record(0, AGENT_A))
        rates = m.rolling_win_rate(window=10, agent_id=AGENT_A)
        assert rates == [(0, 1.0)]

    def test_save_load_roundtrip(self, tmp_path: Path):
        m = MetricsCollector()
        m.record_game(_make_record(0, AGENT_A, steps=30))
        m.record_game(_make_record(1, AGENT_B, steps=60))

        path = tmp_path / "metrics.json"
        m.save(path)

        m2 = MetricsCollector()
        m2.load(path)
        assert len(m2.records) == 2
        assert m2.records[0].winner_id == AGENT_A
        assert m2.records[0].steps == 30
        assert m2.records[0].p1_phi_after == 340.0
        assert m2.records[1].winner_id == AGENT_B
        assert m2.records[1].steps == 60
        assert m2.records[1].p2_phi_after == 345.0

    def test_records_property(self):
        m = MetricsCollector()
        m.record_game(_make_record(0, AGENT_A))
        m.record_game(_make_record(1, AGENT_B))
        assert len(m.records) == 2
        assert m.records[0].game_id == 0
        assert m.records[1].game_id == 1
