"""Tests for bench.charting module."""

from pathlib import Path

from ptcgbench.bench.charting import plot_eval_metrics
from ptcgbench.bench.metrics import GameMetrics, MetricsCollector

AGENT_A = "agent_a"
AGENT_B = "agent_b"


def _make_collector(n_games: int = 5, winner_pattern: str = "alternate") -> MetricsCollector:
    """Build a MetricsCollector with some dummy games."""
    mc = MetricsCollector()
    for i in range(n_games):
        if winner_pattern == "all_wins":
            w = AGENT_A
        elif winner_pattern == "all_losses":
            w = AGENT_B
        else:
            w = AGENT_A if i % 2 == 0 else AGENT_B
        mc.record_game(
            GameMetrics(
                game_id=i,
                batch_id=i // 5,
                p1_id=AGENT_A,
                p2_id=AGENT_B,
                winner_id=w,
                steps=50 + i,
                timestamp="2026-04-06T00:00:00",
                p1_rating_before=1500.0 + i,
                p1_rating_after=1500.0 + i + 10,
                p2_rating_before=1500.0,
                p2_rating_after=1500.0,
                p1_phi_before=350.0,
                p1_phi_after=340.0 - i,
                p2_phi_before=350.0,
                p2_phi_after=345.0 - i,
            )
        )
    return mc


class TestPlotEvalMetrics:
    def test_produces_valid_figure(self, tmp_path: Path) -> None:
        mc = _make_collector(n_games=10, winner_pattern="alternate")
        out = tmp_path / "chart.png"
        result = plot_eval_metrics(mc, out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0

    def test_single_game(self, tmp_path: Path) -> None:
        mc = MetricsCollector()
        mc.record_game(
            GameMetrics(
                game_id=0,
                batch_id=0,
                p1_id=AGENT_A,
                p2_id=AGENT_B,
                winner_id=AGENT_A,
                steps=30,
                timestamp="2026-04-06T00:00:00",
                p1_rating_before=1500.0,
                p1_rating_after=1510.0,
                p2_rating_before=1500.0,
                p2_rating_after=1490.0,
                p1_phi_before=350.0,
                p1_phi_after=325.0,
                p2_phi_before=350.0,
                p2_phi_after=330.0,
            )
        )
        out = tmp_path / "chart.png"
        result = plot_eval_metrics(mc, out)
        assert result == out
        assert out.exists()

    def test_zero_games_produces_no_file(self, tmp_path: Path) -> None:
        mc = MetricsCollector()
        out = tmp_path / "chart.png"
        plot_eval_metrics(mc, out)
        assert not out.exists()

    def test_all_draws(self, tmp_path: Path) -> None:
        mc = MetricsCollector()
        for i in range(5):
            mc.record_game(
                GameMetrics(
                    game_id=i,
                    batch_id=0,
                    p1_id=AGENT_A,
                    p2_id=AGENT_B,
                    winner_id="draw",
                    steps=100,
                    timestamp="2026-04-06T00:00:00",
                    p1_rating_before=1500.0 + i,
                    p1_rating_after=1500.0 + i + 5,
                    p2_rating_before=1500.0,
                    p2_rating_after=1500.0,
                    p1_phi_before=350.0,
                    p1_phi_after=345.0 - i,
                    p2_phi_before=350.0,
                    p2_phi_after=348.0 - i,
                )
            )
        out = tmp_path / "chart.png"
        plot_eval_metrics(mc, out)
        assert out.exists()

    def test_custom_window(self, tmp_path: Path) -> None:
        mc = _make_collector(n_games=20, winner_pattern="all_wins")
        out = tmp_path / "chart.png"
        plot_eval_metrics(mc, out, window=5)
        assert out.exists()

    def test_title_includes_agent_ids_and_deck(self, tmp_path: Path) -> None:
        mc = _make_collector(n_games=3)
        out = tmp_path / "chart.png"
        plot_eval_metrics(mc, out, agent_ids=[AGENT_A, AGENT_B], deck="charizard_ex")
        assert out.exists()

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        mc = _make_collector(n_games=3)
        out = tmp_path / "nested" / "dir" / "chart.png"
        plot_eval_metrics(mc, out)
        assert out.exists()
