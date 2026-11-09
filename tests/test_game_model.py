"""Game model and player-level uncertainty tests (sim-accuracy Stage 4)."""
import math

import numpy as np
import pytest

from tradesim import game_model
from tradesim.engine import Engine, draw_impacts
from tradesim.game_model import back_to_backs, fit_probit, load_model, norm_cdf, win_probability
from tradesim.games import load_schedule_2026_27
from tradesim.league import League
from tradesim.model import load_sim_config
from tradesim.ratings import load_ratings


@pytest.fixture(scope="module")
def model():
    return load_model()


def test_norm_cdf_is_accurate():
    for x in np.linspace(-6, 6, 241):
        assert norm_cdf(x) == pytest.approx(0.5 * (1 + math.erf(x / math.sqrt(2))), abs=2e-7)


def test_probit_recovers_known_constants():
    rng = np.random.default_rng(0)
    n = 40000
    x = np.column_stack([rng.normal(0, 6, n), np.ones(n), rng.integers(-1, 2, n)])
    true = np.array([1 / 12, 2.5 / 12, 1.5 / 12])
    y = (rng.random(n) < norm_cdf(x @ true)).astype(float)
    beta, _ = fit_probit(x, y)
    assert 1 / beta[0] == pytest.approx(12, rel=0.05)
    assert beta[1] / beta[0] == pytest.approx(2.5, abs=0.3)
    assert beta[2] / beta[0] == pytest.approx(1.5, abs=0.4)


def test_fitted_constants_are_in_expected_ranges(model):
    assert model["fit_seasons"] == game_model.FIT_SEASONS and model["games"] > 8000
    assert 1.0 < model["home_edge"] < 3.5
    assert 0.5 < model["b2b_penalty"] < 3.5
    assert 10 < model["sigma"] < 15
    m = model["margin_regression"]  # the cross-check agrees
    assert abs(m["home_edge"] - model["home_edge"]) < 0.5 and abs(m["b2b_penalty"] - model["b2b_penalty"]) < 0.5


def test_saved_model_matches_a_fresh_fit(model):
    """Refit with `python -m tradesim.game_model` after changing game data."""
    fresh = game_model.fit(write=False)
    assert fresh["home_edge"] == model["home_edge"] and fresh["sigma"] == model["sigma"]


def test_model_works_on_a_season_it_was_not_fitted_on(model):
    assert model["check_2025_26"]["accuracy"] > 0.6
    assert model["check_2025_26"]["brier"] < 0.23


def test_win_probability_basics(model):
    assert win_probability(0.0, 0.0, 0, 0, model) == pytest.approx(0.5)
    home = win_probability(0.0, 1.0, 0, 0, model)
    assert home == pytest.approx(norm_cdf(model["home_edge"] / model["sigma"]))
    assert win_probability(0.0, 1.0, 1, 0, model) < home < win_probability(0.0, 1.0, 0, 1, model)


def test_back_to_back_detection():
    games = [{"home": "BOS", "away": "NYK", "date": "2026-11-01"},
             {"home": "PHI", "away": "BOS", "date": "2026-11-02"},
             {"home": "NYK", "away": "MIA", "date": "2026-11-04"},
             {"home": "NYK", "away": "ATL", "date": None}]
    home, away = back_to_backs(games)
    assert list(home) == [0, 0, 0, 0] and list(away) == [0, 1, 0, 0]


def test_player_impacts_are_drawn_per_player_not_fixed():
    ratings = load_ratings()
    draws = draw_impacts(["nikola-jokic", "tyrese-haliburton"], ratings, 20000, seed=7)
    for pid, d in draws.items():
        assert d.mean() == pytest.approx(ratings["players"][pid]["impact"], abs=0.05)
        assert d.std() == pytest.approx(ratings["players"][pid]["se"], rel=0.05)
    again = draw_impacts(["tyrese-haliburton"], ratings, 20000, seed=7)
    assert np.array_equal(again["tyrese-haliburton"], draws["tyrese-haliburton"])


def test_team_strength_varies_between_simulated_seasons():
    engine = Engine(League.load(), load_schedule_2026_27(), load_sim_config(), n_sims=1000)
    full = engine.baseline_strengths["DEN"].max(axis=1)  # best game each season ~ full strength
    assert full.std() > 0.5
    u = engine.uncertainty()
    assert 1.5 < u["season_strength_sd"] < 4.5


# --- shared team-season error (Stage 4 revision) ----------------------------------------------

def test_sigma_t_closes_the_gap_to_the_measured_spread():
    import json
    from tradesim.engine import UNCERTAINTY_PATH
    u = json.load(open(UNCERTAINTY_PATH))
    assert u["sigma_t"] == pytest.approx(math.sqrt(u["target_latent_sd"] ** 2 - u["sim_sd_without_team_term"] ** 2),
                                         abs=0.01)
    engine = Engine(League.load(), load_schedule_2026_27(), load_sim_config(), n_sims=4000)
    assert engine.uncertainty()["season_strength_sd"] == pytest.approx(u["target_latent_sd"], abs=0.15)


def test_interval_coverage_after_adding_sigma_t():
    import json
    from tradesim.engine import UNCERTAINTY_PATH
    u = json.load(open(UNCERTAINTY_PATH))
    assert u["coverage_before"]["80%"]["share"] < 0.75          # too narrow without the team term
    assert 0.75 <= u["coverage_after"]["80%"]["share"] <= 0.85
    assert 0.44 <= u["coverage_after"]["50%"]["share"] <= 0.56


def test_luck_uses_fitted_game_spread():
    import json
    from tradesim.strength_check import CHECK_PATH
    check = json.load(open(CHECK_PATH))
    assert 1.2 < check["game_luck_sd"] < 1.6     # about sigma / sqrt(82), more for short seasons
    assert check["strength_sd"] > check["strength_sd_first_version"]


def test_team_season_errors_are_zero_sum_with_sd_sigma_t():
    from tradesim.engine import team_season_errors
    e = team_season_errors(2.0, 20000, seed=11)
    assert np.abs(e.sum(axis=1)).max() < 1e-9
    assert e.std(axis=0).mean() == pytest.approx(2.0, rel=0.02)


def test_league_wins_total_1230_every_simulated_season():
    engine = Engine(League.load(), load_schedule_2026_27(), load_sim_config(), n_sims=1000)
    assert (engine.baseline()["wins"].sum(axis=1) == 1230).all()


def test_leave_one_season_out_coverage_and_playoff_calibration():
    import json
    from tradesim.engine import UNCERTAINTY_PATH
    u = json.load(open(UNCERTAINTY_PATH))
    pooled = u["loso"]["pooled"]
    assert pooled["80%"]["of"] == 210
    assert 0.75 <= pooled["80%"]["share"] <= 0.85 and 0.44 <= pooled["50%"]["share"] <= 0.56
    assert all(1.5 < f["sigma_t"] < 3.2 for f in u["loso"]["folds"].values())
    calib = u["playoff_calibration"]
    for row in calib["table"]:
        if row["teams"] >= 30:  # small buckets are too noisy to check
            assert abs(row["predicted"] - row["actual"]) < 0.12, row
    assert calib["brier"] < calib["brier_base_rate"]


def test_playoff_calibration_is_reproducible():
    import json
    from tradesim import calibrate
    from tradesim.game_model import load_model
    u = json.load(open(calibrate.UNCERTAINTY_PATH))
    errors = json.load(open(calibrate.CHECK_PATH))["team_season_errors"]
    errors = [e for e in errors if e["season"] in ("2023-24", "2024-25")]
    a = calibrate.playoff_calibration(errors, u["sim_sd_without_team_term"], load_model()["sigma"], n_sims=500)
    b = calibrate.playoff_calibration(errors, u["sim_sd_without_team_term"], load_model()["sigma"], n_sims=500)
    assert a == b
