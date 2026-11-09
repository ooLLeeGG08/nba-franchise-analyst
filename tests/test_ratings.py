"""Player rating model tests (sim-accuracy Stage 2)."""
import json
import math
import os

import pytest

from tradesim import ratings
from tradesim.league import League
from tradesim.model import league_strengths, load_sim_config, team_strength
from tradesim.ratings import (load_fit, load_ratings, normalize_minutes, posterior, raw_prior, rotation_minutes)


@pytest.fixture(scope="module")
def cfg():
    return load_sim_config()


@pytest.fixture(scope="module")
def fitted():
    return load_fit()


@pytest.fixture(scope="module")
def league():
    return League.load()


# --- the fitted model makes sense -----------------------------------------------------------

def test_fit_values_are_sensible(fitted, cfg):
    v, rk, u = fitted["veterans"], fitted["rookies"], fitted["uncertainty"]
    grid = cfg["ratings"]["grid"]
    # Chosen values are inside the search grid, not stuck at an edge.
    assert grid["shrink_minutes"][0] < v["shrink_minutes"] < grid["shrink_minutes"][-1]
    assert grid["prior_mean"][0] < v["prior_mean"] < grid["prior_mean"][-1]
    assert 0 < v["recency"] <= 1
    # Young players improve, old players decline.
    assert v["age_adjustment"][0] > 0 > v["age_adjustment"][-1]
    # Earlier picks are better rookies.
    assert rk["bpm_per_log_pick"] < 0
    assert u["tau_rookie"] >= u["tau_veteran"] > 0 and u["K_minutes"] > 0
    assert 0 <= fitted["team_residual"]["rho"] <= 1
    assert 0.5 < fitted["availability"]["mean"] < 0.9


def test_saved_fit_matches_a_fresh_fit(fitted, cfg):
    """Refit with `python -m tradesim.ratings` after changing data or settings."""
    fresh = ratings.fit(cfg, write=False)
    assert fresh["veterans"] == fitted["veterans"]
    assert fresh["uncertainty"] == fitted["uncertainty"]


# --- formulas -----------------------------------------------------------------------------------

def test_raw_prior_shrinks_toward_mu():
    hist = [(1, {"bpm": 6.0, "mp": 300})]
    assert raw_prior(hist, 0.5, 300, -2.0) == pytest.approx(2.0)
    assert raw_prior([], 0.5, 300, -2.0) == -2.0


def test_posterior_weight_is_minutes_over_minutes_plus_k(fitted):
    u = fitted["uncertainty"]
    tau, c, k = u["tau_veteran"], u["c"], u["c"] / u["tau_veteran"] ** 2
    impact, se = posterior(1.0, tau, 5.0, 300, c)
    w = 300 / (300 + k)
    assert impact == pytest.approx((1 - w) * 1.0 + w * 5.0)
    assert se < tau
    assert posterior(1.0, tau, None, None, c) == (1.0, tau)


def test_rotation_keeps_stars_minutes_and_sums_to_240():
    mpgs = {"star": 36, **{f"p{i}": 25 for i in range(12)}}
    out = rotation_minutes(mpgs, 240, 42)
    assert sum(out.values()) == pytest.approx(240)
    assert out["star"] == 36


def test_short_rotation_scales_up_within_cap():
    out = rotation_minutes({"a": 30, "b": 30, "c": 20}, 240, 42)
    assert sum(out.values()) == pytest.approx(126)  # capped at 42 each: can't reach 240 with 3 players
    out = normalize_minutes({f"p{i}": 20 for i in range(8)}, 240, 42)
    assert sum(out.values()) == pytest.approx(240)


# --- 2026-27 ratings and team strength ------------------------------------------------------------

def test_every_rostered_player_is_rated(league):
    rated = load_ratings()["players"]
    assert set(rated) == set(league.players)
    for r in rated.values():
        assert math.isfinite(r["impact"]) and r["se"] > 0 and 0 < r["availability"] <= 1


def test_team_strength_is_player_sum_plus_residual(league, cfg):
    rated = load_ratings()
    strength, breakdown = team_strength("DEN", league.roster("DEN"), cfg)
    exact = rotation_minutes({p["id"]: rated["players"][p["id"]]["mpg_projected"] for p in league.roster("DEN")},
                             240, cfg["ratings"]["max_mpg"])
    assert sum(exact.values()) == pytest.approx(240)
    assert sum(b["minutes"] for b in breakdown) == pytest.approx(240, abs=0.5)  # breakdown rounds to 0.1
    expected = sum(rated["players"][b["id"]]["impact"] * b["minutes"] / 48 for b in breakdown)
    assert strength == pytest.approx(expected + rated["team_residuals"]["DEN"]["residual"], abs=0.05)


def test_moving_a_player_changes_both_teams(league, cfg):
    jokic = league.players["nikola-jokic"]
    den_without = team_strength("DEN", [p for p in league.roster("DEN") if p["id"] != jokic["id"]], cfg)[0]
    atl_with = team_strength("ATL", league.roster("ATL") + [jokic], cfg)[0]
    base = league_strengths(league, cfg, ["DEN", "ATL"])
    assert den_without < base["DEN"] and atl_with > base["ATL"]


def test_team_residual_is_small_and_stays_with_team():
    res = load_ratings()["team_residuals"]
    assert all(abs(r["residual"]) < 2 for r in res.values())


# --- validation and data provenance ------------------------------------------------------------------

def test_ratings_are_calibrated_with_actual_minutes(cfg):
    from tradesim.strength_check import run
    r, _ = run(cfg, write=False)
    assert 0.85 <= r["pooled"]["new_actual_min"]["slope"] <= 1.15
    assert r["pooled"]["new_actual_min"]["mae"] < r["pooled"]["old_actual_min"]["mae"]


def test_every_raw_file_has_source_and_as_of():
    raw = os.path.join(ratings.ROOT, "data", "raw")
    manifest = json.load(open(os.path.join(raw, "SOURCES.json")))["files"]
    on_disk = {os.path.relpath(os.path.join(d, f), raw) for d, _, fs in os.walk(raw) for f in fs if f != "SOURCES.json"}
    assert on_disk == set(manifest)
    assert all(v["source_url"] and v["as_of"] for v in manifest.values())
