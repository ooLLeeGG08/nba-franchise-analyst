"""Step 3 of the simulator: Monte Carlo seasons, vectorized with numpy.

For every game, the win probability comes from the fitted model (tradesim.fit).
One season = one biased coin flip per game. All seasons are drawn at once:

    uniforms: n_seasons x n_games random numbers in [0, 1)
    home_won = uniforms < p                      (n_seasons x n_games, True/False)
    wins     = home_won @ HOME + (~home_won) @ AWAY

HOME / AWAY are n_games x 30 one-hot matrices (which team is home/away in each game),
so the matrix product counts each team's wins in every season at once.

Comparisons (before vs after trades) reuse the same random numbers ("common random
numbers"), so the difference comes from the trade, not from luck.
"""
import numpy as np

from tradesim.fit import load_fit
from tradesim.model import league_strengths, load_sim_config
from tradesim.teams import TEAM_INFO

CODES = list(TEAM_INFO)
INDEX = {c: i for i, c in enumerate(CODES)}


def _schedule_arrays(schedule):
    home = np.array([INDEX[g["home"]] for g in schedule])
    away = np.array([INDEX[g["away"]] for g in schedule])
    neutral = np.array([g["neutral"] for g in schedule])
    n = len(schedule)
    home_onehot = np.zeros((n, len(CODES)), dtype=np.float32)
    away_onehot = np.zeros((n, len(CODES)), dtype=np.float32)
    home_onehot[np.arange(n), home] = 1
    away_onehot[np.arange(n), away] = 1
    return home, away, neutral, home_onehot, away_onehot


def win_probabilities(schedule, strengths, fit):
    home, away, neutral, _, _ = _schedule_arrays(schedule)
    s = np.array([strengths[c] for c in CODES])
    logit = fit["home"] * (~neutral) + fit["slope"] * (s[home] - s[away])
    return 1 / (1 + np.exp(-logit))


def draw_uniforms(n_games, cfg):
    rng = np.random.default_rng(cfg["simulation"]["seed"])
    return rng.random((cfg["simulation"]["n_seasons"], n_games), dtype=np.float32)


def simulate_season(schedule, strengths, fit, cfg, uniforms=None):
    """Simulate the season many times. Returns {team: summary} plus the raw wins matrix."""
    _, _, _, home_onehot, away_onehot = _schedule_arrays(schedule)
    p = win_probabilities(schedule, strengths, fit).astype(np.float32)
    if uniforms is None:
        uniforms = draw_uniforms(len(schedule), cfg)
    home_won = (uniforms < p).astype(np.float32)
    wins = home_won @ home_onehot + (1 - home_won) @ away_onehot  # n_seasons x 30
    wins = np.rint(wins).astype(np.int16)
    seeds = _seeds(wins, cfg)
    return {"teams": _summaries(wins, seeds, cfg), "wins": wins, "seeds": seeds}


def _seeds(wins, cfg):
    """Conference seed (1-15) of each team in each simulated season. Ties are broken at
    random (the NBA's real tiebreakers need head-to-head records, not modelled)."""
    rng = np.random.default_rng(cfg["simulation"]["seed"] + 1)
    jitter = rng.random(wins.shape)
    seeds = np.zeros(wins.shape, dtype=np.int8)
    for conference in ("East", "West"):
        cols = np.array([INDEX[c] for c in CODES if TEAM_INFO[c]["conference"] == conference])
        key = wins[:, cols] + jitter[:, cols] * 0.5
        order = np.argsort(-key, axis=1)
        ranks = np.empty_like(order)
        ranks[np.arange(len(order))[:, None], order] = np.arange(1, len(cols) + 1)
        seeds[:, cols] = ranks
    return seeds


def _summaries(wins, seeds, cfg):
    sim = cfg["simulation"]
    lo, hi = sim["range_percentiles"]
    out = {}
    for c in CODES:
        w, s = wins[:, INDEX[c]], seeds[:, INDEX[c]]
        out[c] = {
            "mean_wins": round(float(w.mean()), 1),
            "range": [int(np.percentile(w, lo)), int(np.percentile(w, hi))],
            "distribution": np.bincount(w, minlength=83)[:83].tolist(),
            "seed_frequency": [round(float(np.mean(s == k)), 4) for k in range(1, 16)],
            "playoff_pct": round(float(np.mean(s <= sim["playoff_seeds"])), 4),
            "play_in_pct": round(float(np.mean((s > sim["playoff_seeds"]) & (s <= sim["play_in_seeds"]))), 4),
        }
    return out


def compare(schedule, before, after, fit, cfg, teams=None):
    """Simulate with `before` and `after` strengths using the same random numbers.
    Returns per-team before/after summaries and the change in average wins."""
    uniforms = draw_uniforms(len(schedule), cfg)
    b = simulate_season(schedule, before, fit, cfg, uniforms)
    a = simulate_season(schedule, after, fit, cfg, uniforms)
    out = {}
    for c in teams or CODES:
        out[c] = {"before": b["teams"][c], "after": a["teams"][c],
                  "win_change": round(a["teams"][c]["mean_wins"] - b["teams"][c]["mean_wins"], 1),
                  "strength_before": round(before[c], 2), "strength_after": round(after[c], 2)}
    return out


def simulate_trades(league, cba, trades, schedule, on_date=None, cfg=None, fit=None):
    """Check `trades` in order, apply the ones that work, and simulate 2026-27 before and
    after. Only teams in working trades change; every other roster stays as it is.
    Draft picks don't change team strength."""
    from tradesim.checker import check_trades_in_sequence
    cfg = cfg or load_sim_config()
    fit = fit or load_fit()
    results, final = check_trades_in_sequence(league, cba, trades, on_date)
    changed = sorted({code for r in results if r["works"] for code in r["teams"]})
    before = league_strengths(league, cfg)
    after = dict(before)
    after.update(league_strengths(final, cfg, changed))
    return {"checks": results, "changed_teams": changed,
            "teams": compare(schedule, before, after, fit, cfg)}
