"""Simulator tests: player value, minutes, fit, Monte Carlo, trades, backtest."""
import time

import numpy as np
import pytest

from tradesim import backtest
from tradesim.fit import fit, fit_logistic, load_fit
from tradesim.games import load_results_2025_26, load_schedule_2026_27, schedule_from_results
from tradesim.league import player_id, League, load_cba
from tradesim.model import (allocate_minutes, expected_mpg, league_strengths, load_sim_config, player_value,
                            team_strength)
from tradesim.simulate import CODES, compare, simulate_season, simulate_trades
from tradesim.teams import TEAM_INFO


@pytest.fixture(scope="module")
def cfg():
    return load_sim_config()


@pytest.fixture(scope="module")
def league():
    return League.load()


@pytest.fixture(scope="module")
def schedule():
    return load_schedule_2026_27()


# --- step 1: player value and minutes ---------------------------------------------------

def test_player_value_shrinks_small_samples_to_replacement(cfg):
    assert player_value(None, None, cfg) == -2.0
    assert player_value(10.0, 2000, cfg) == pytest.approx((10 * 2000 - 2 * 250) / 2250)
    # 20 minutes of +15 BPM barely moves the needle.
    assert player_value(15.0, 20, cfg) < 0


def test_minutes_fill_240_by_expected_minutes(cfg):
    # Expected minutes add up to 260. In order (36, 34, 32, 30, 28, 26, 22, 20) the first 8 get
    # theirs (228); "h" (18) gets the last 12; "j" (14) gets none.
    mins = allocate_minutes({"a": 36, "b": 34, "c": 32, "d": 30, "e": 28, "f": 26, "g": 22, "h": 18,
                             "i": 20, "j": 14}, cfg)
    assert sum(mins.values()) == pytest.approx(240)
    assert mins["a"] == 36 and mins["i"] == 20 and mins["h"] == 12 and mins["j"] == 0


def test_short_roster_minutes_scale_up(cfg):
    mins = allocate_minutes({"a": 30, "b": 30, "c": 30, "d": 30, "e": 30, "f": 30}, cfg)
    assert sum(mins.values()) == pytest.approx(240)


def test_rookie_minutes_by_draft_pick(cfg):
    top_pick = {"acquired": {"type": "draft", "draft_year": 2026, "pick": 1}}
    late_pick = {"acquired": {"type": "draft", "draft_year": 2026, "pick": 25}}
    assert expected_mpg(top_pick, cfg) > expected_mpg(late_pick, cfg)


def test_better_player_raises_team_strength(league, cfg):
    roster = league.roster("ATL")
    base, _ = team_strength("ATL", roster, cfg)
    star = league.players[player_id("nikola-jokic")]
    stronger, _ = team_strength("ATL", roster + [star], cfg)
    assert stronger > base


# --- step 2: fitted win probability -----------------------------------------------------------

def test_fit_recovers_known_constants():
    rng = np.random.default_rng(0)
    x = np.column_stack([np.ones(20000), rng.normal(0, 8, 20000)])
    p = 1 / (1 + np.exp(-(x @ np.array([0.3, 0.12]))))
    y = (rng.random(20000) < p).astype(float)
    home, slope = fit_logistic(x, y)
    assert home == pytest.approx(0.3, abs=0.05) and slope == pytest.approx(0.12, abs=0.01)


def test_fit_on_2025_26_is_sensible(cfg):
    r = fit(cfg, write=False)
    assert r["games"] == 1230
    assert 0.53 < r["home_win_prob_even_teams"] < 0.62
    assert 0.08 < r["slope"] < 0.2
    assert r["log_loss"] < r["log_loss_home_court_only"]


def test_saved_fit_matches_a_fresh_fit(cfg):
    """data/model/fit.json must be refitted after changing data or settings: python -m tradesim.fit"""
    saved, fresh = load_fit(), fit(cfg, write=False)
    assert saved["home"] == pytest.approx(fresh["home"]) and saved["slope"] == pytest.approx(fresh["slope"])


# --- step 3: Monte Carlo --------------------------------------------------------------------------

def test_schedule_has_82_games_per_team(schedule):
    counts = {c: 0 for c in TEAM_INFO}
    for g in schedule:
        counts[g["home"]] += 1
        counts[g["away"]] += 1
        assert g["home"] != g["away"]
    assert set(counts.values()) == {82} and len(schedule) == 1230
    filler = [g for g in schedule if g["placeholder"]]
    assert len(filler) == 30
    assert all(TEAM_INFO[g["home"]]["conference"] == TEAM_INFO[g["away"]]["conference"] for g in filler)


def test_season_totals_and_speed(league, cfg, schedule):
    strengths = league_strengths(league, cfg)
    start = time.time()
    sim = simulate_season(schedule, strengths, load_fit(), cfg)
    assert time.time() - start < 3
    assert sim["wins"].shape == (cfg["simulation"]["n_seasons"], 30)
    assert (sim["wins"].sum(axis=1) == 1230).all()
    for t in sim["teams"].values():
        assert t["range"][0] <= t["mean_wins"] <= t["range"][1]
        assert sum(t["distribution"]) == cfg["simulation"]["n_seasons"]
        assert sum(t["seed_frequency"]) == pytest.approx(1.0)


def test_equal_teams_average_41_wins(cfg, schedule):
    even = {c: 0.0 for c in CODES}
    sim = simulate_season(schedule, even, {"home": 0.0, "slope": 0.13}, cfg)
    assert all(abs(t["mean_wins"] - 41) < 1 for t in sim["teams"].values())


def test_simulation_is_reproducible(league, cfg, schedule):
    s = league_strengths(league, cfg)
    a = simulate_season(schedule, s, load_fit(), cfg)["teams"]["BOS"]
    b = simulate_season(schedule, s, load_fit(), cfg)["teams"]["BOS"]
    assert a == b


def test_no_change_means_no_difference(league, cfg, schedule):
    s = league_strengths(league, cfg)
    out = compare(schedule, s, s, load_fit(), cfg)
    assert all(t["win_change"] == 0 for t in out.values())


# --- trades ------------------------------------------------------------------------------------------

def test_only_traded_teams_change_strength(league, cfg, schedule):
    mv = lambda pid, f, t: {"type": "player", "id": pid, "from": f, "to": t}
    out = simulate_trades(league, load_cba(), [{"moves": [mv(player_id("tyrese-maxey"), "PHI", "ATL"),
                                                          mv(player_id("jalen-johnson"), "ATL", "PHI"),
                                                          mv(player_id("aaron-wiggins"), "ATL", "PHI")]}],
                          schedule, "2026-11-09", cfg)
    assert out["changed_teams"] == ["ATL", "PHI"]
    for code, t in out["teams"].items():
        if code not in ("ATL", "PHI"):
            assert t["strength_before"] == t["strength_after"]
    assert out["teams"]["ATL"]["win_change"] > 0
    # Philadelphia is weaker at full health; over a season the 2-for-1 depth (players miss about
    # 30% of games) can make up for it, so its win change isn't asserted.
    assert out["teams"]["PHI"]["full_strength_after"] < out["teams"]["PHI"]["full_strength_before"]


def test_failed_trade_changes_nothing(league, cfg, schedule):
    mv = lambda pid, f, t: {"type": "player", "id": pid, "from": f, "to": t}
    out = simulate_trades(league, load_cba(), [{"moves": [mv(player_id("joel-embiid"), "PHI", "ATL"),
                                                          mv(player_id("jalen-johnson"), "ATL", "PHI")]}],
                          schedule, "2026-11-09", cfg)
    assert out["changed_teams"] == []
    assert all(t["win_change"] == 0 for t in out["teams"].values())


def test_picks_do_not_change_strength(league, cfg, schedule):
    pick = next(p for p in league.picks.values() if p["holder"] == "BKN" and p["kind"] == "own" and p["round"] == 2)
    mv = lambda pid, f, t: {"type": "player", "id": pid, "from": f, "to": t}
    out = simulate_trades(league, load_cba(), [{"moves": [mv(player_id("danny-wolf"), "BKN", "MIN"),
                                                          mv(player_id("joan-beringer"), "MIN", "BKN")]}], schedule, "2026-11-09", cfg)
    with_pick = simulate_trades(league, load_cba(), [{"moves": [mv(player_id("danny-wolf"), "BKN", "MIN"),
                                                                mv(player_id("joan-beringer"), "MIN", "BKN"),
                                                                {"type": "pick", "id": pick["id"], "from": "BKN",
                                                                 "to": "MIN"}]}], schedule, "2026-11-09", cfg)
    assert out["teams"]["BKN"]["strength_after"] == with_pick["teams"]["BKN"]["strength_after"]


# --- backtest ------------------------------------------------------------------------------------------

def test_backtest_beats_naive_guess(cfg):
    r = backtest.run(cfg, write=False)
    assert len(schedule_from_results(load_results_2025_26())) == 1230
    naive = r["naive_41_wins"]["mae"]
    for name, v in r["versions"].items():
        if v["in_sample"]:
            assert v["mae"] < 4.0, name
        else:
            assert v["mae"] < naive * 0.8, name  # forecasts from 2024-25 stats
    assert r["strength_uncertainty"]["strength_sd_points"] > 0


def test_injured_players_keep_their_rating_from_earlier_seasons(league, cfg):
    """Haliburton missed 2025-26; his rating comes from 2024-25 and earlier (BPM +5.8 in 2024-25),
    while the missed season lowers his expected share of games played."""
    _, breakdown = team_strength("IND", league.roster("IND"), cfg)
    hali = next(b for b in breakdown if b["id"] == player_id("tyrese-haliburton"))
    assert hali["impact"] > 3
    assert hali["minutes"] > 10


def test_strength_uncertainty_widens_ranges_but_keeps_totals(league, cfg, schedule):
    from tradesim.simulate import load_strength_sd
    s = league_strengths(league, cfg)
    sd = load_strength_sd()
    assert 1 < sd < 8
    luck_only = simulate_season(schedule, s, load_fit(), cfg)
    with_sd = simulate_season(schedule, s, load_fit(), cfg, strength_sd=sd)
    assert (with_sd["wins"].sum(axis=1) == 1230).all()
    width = lambda sim: np.mean([t["range"][1] - t["range"][0] for t in sim["teams"].values()])
    assert width(with_sd) > width(luck_only) * 1.5


def test_same_offsets_before_and_after_mean_no_phantom_change(league, cfg, schedule):
    s = league_strengths(league, cfg)
    out = compare(schedule, s, s, load_fit(), cfg, strength_sd=3.5)
    assert all(t["win_change"] == 0 for t in out.values())
