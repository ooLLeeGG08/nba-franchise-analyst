"""Stage 7 backtest tests: scoring functions, a fast smoke test, and the saved results."""
import json

import numpy as np
import pytest

from tradesim import backtest_nov9 as bt
from tradesim.model import load_sim_config


def test_rps_and_pit():
    dist = np.zeros(83)
    dist[40] = 1.0  # certain: exactly 40 wins
    assert bt._rps(dist, 40) == 0 and bt._rps(dist, 42) == 2
    assert bt._mid_pit(dist, 40) == 0.5
    wide = np.ones(83)
    assert bt._rps(wide, 41) < bt._rps(wide, 5)  # a central outcome scores better than an extreme one


@pytest.fixture(scope="module")
def report():
    with open(bt.OUT_PATH) as f:
        return json.load(f)


def test_backtest_covers_five_seasons_held_out(report):
    assert report["seasons"] == ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
    for season, fits in report["left_out_fits"].items():
        assert 1.0 < fits["game_model"]["home_edge"] < 3.5


def test_win_totals_beat_naive_and_slope_near_one(report):
    m = report["loso"]
    assert m["teams"] == 150
    assert m["win_mae"] < 9.0  # guessing 41 wins for everyone: about 10.1
    assert 0.85 <= m["slope"] <= 1.15


def test_sigma_t_interior_and_held_out_coverage(report):
    grid = [float(s) for s in report["sigma_grid"]]
    assert grid[0] < report["sigma_t"] < grid[-1]
    assert 0.72 <= report["loso"]["inside_80"] <= 0.88
    assert 0.44 <= report["loso"]["inside_50"] <= 0.58
    assert report["loso"]["playoff_brier"] < report["loso"]["playoff_brier_base_rate"]


def test_playoff_calibration_within_noise(report):
    for row in report["loso_calibration"]:
        if row["teams"] >= 25:
            assert abs(row["predicted"] - row["actual"]) < 0.15, row


def test_players_not_underdispersed(report):
    """No player SE scale factor: players land inside their intervals about as often as they should."""
    for season, v in report["players_check"].items():
        assert v["inside_80"] >= 0.72, season


def test_engine_uses_backtest_sigma_t(report):
    from tradesim.engine import load_team_season_sd
    assert load_team_season_sd() == report["sigma_t"]


def test_build_season_smoke():
    cfg = load_sim_config()
    from tradesim import ratings
    league, rated, asof = bt.build_season("2024-25", ratings.load_fit(), cfg)
    assert len(league.players) > 400
    assert all(len(league.roster(c)) >= 8 for c in league.teams)
    assert len(asof["playoff_teams"]) == 16
    assert all(abs(r["residual"]) < 3 for r in rated["team_residuals"].values())


def test_vegas_file_is_complete_and_sourced():
    import csv
    with open(bt.VEGAS_PATH) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 150
    by_season = {}
    for r in rows:
        assert r["source_url"].startswith("https://www.basketball-reference.com/leagues/NBA_")
        by_season.setdefault(r["season"], []).append(float(r["total"]))
    assert sorted(by_season) == bt.SEASONS
    for season, totals in by_season.items():
        assert len(totals) == 30
        assert 1215 <= sum(totals) <= 1260, season  # sportsbook totals sum a little above 1,230


def test_vegas_comparison_reported_side_by_side(report):
    v = report["vegas"]
    assert v["status"] == "ok" and v["teams"] == 150
    for side in ("model", "vegas"):
        assert {"win_mae", "playoff_brier", "slope", "slope_90ci"} <= set(v[side])
        lo, hi = v[side]["slope_90ci"]
        assert lo <= v[side]["slope"] <= hi


def test_slope_tracking():
    """Track the held-out slope: if it drops below about 0.95, consider shrinking toward 41."""
    with open(bt.OUT_PATH) as f:
        r = json.load(f)
    assert r["loso"]["slope"] >= 0.9
    lo, hi = r["vegas"]["model"]["slope_90ci"]
    assert lo < 1.0 < hi or r["loso"]["slope"] >= 0.95
