"""Step 3 of the simulator: Monte Carlo seasons, vectorized with numpy.

For every game, the win probability comes from the fitted model (tradesim.fit).
One season = one biased coin flip per game. All seasons are drawn at once:

    uniforms: n_seasons x n_games random numbers in [0, 1)
    home_won = uniforms < p                      (n_seasons x n_games, True/False)
    wins     = home_won @ HOME + (~home_won) @ AWAY

HOME / AWAY are n_games x 30 one-hot matrices (which team is home/away in each game),
so the matrix product counts each team's wins in every season at once.

Team-strength uncertainty: each simulated season also shifts every team's strength
by a random amount (spread measured by the forecast backtest), so the win ranges
include "we don't know exactly how good this team is", not just game luck.

Comparisons (before vs after trades) reuse the same random numbers ("common random
numbers"), so the difference comes from the trade, not from luck.
"""
import json

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


def win_probabilities(schedule, strengths, fit, offsets=None):
    """P(home wins) for every game. With `offsets` (n_seasons x 30 strength shifts),
    returns one row of probabilities per simulated season."""
    home, away, neutral, _, _ = _schedule_arrays(schedule)
    s = np.array([strengths[c] for c in CODES])
    if offsets is not None:
        s = s[None, :] + offsets
    logit = fit["home"] * (~neutral) + fit["slope"] * (s[..., home] - s[..., away])
    return 1 / (1 + np.exp(-logit))


def draw_uniforms(n_games, cfg):
    rng = np.random.default_rng(cfg["simulation"]["seed"])
    return rng.random((cfg["simulation"]["n_seasons"], n_games), dtype=np.float32)


def draw_offsets(strength_sd, cfg):
    """Team-strength uncertainty: in each simulated season every team is shifted by a
    random amount (normal, spread = strength_sd points), because we don't know exactly
    how good a team really is. The spread is measured by the forecast backtest."""
    if not strength_sd:
        return None
    rng = np.random.default_rng(cfg["simulation"]["seed"] + 2)
    return rng.normal(0, strength_sd, (cfg["simulation"]["n_seasons"], len(CODES))).astype(np.float32)


def load_strength_sd():
    """Spread of team-strength uncertainty, measured by tradesim.strength_check (forecast
    error of team net ratings over 2019-20 to 2025-26, minus 82-game luck)."""
    from tradesim.strength_check import CHECK_PATH
    with open(CHECK_PATH) as f:
        return json.load(f)["strength_sd"]


def simulate_season(schedule, strengths, fit, cfg, uniforms=None, strength_sd=0.0, offsets=None):
    """Simulate the season many times. Returns {team: summary} plus the raw wins matrix.

    strength_sd=0 simulates game-to-game luck only (used by the backtest, which
    measures the uncertainty). The app passes load_strength_sd() so the ranges
    also include uncertainty about each team's true strength."""
    _, _, _, home_onehot, away_onehot = _schedule_arrays(schedule)
    if offsets is None:
        offsets = draw_offsets(strength_sd, cfg)
    p = win_probabilities(schedule, strengths, fit, offsets).astype(np.float32)
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


def compare(schedule, before, after, fit, cfg, teams=None, strength_sd=0.0):
    """Simulate with `before` and `after` strengths using the same random numbers (and the
    same strength offsets). Returns per-team before/after summaries and the change in
    average wins."""
    uniforms = draw_uniforms(len(schedule), cfg)
    offsets = draw_offsets(strength_sd, cfg)
    b = simulate_season(schedule, before, fit, cfg, uniforms, offsets=offsets)
    a = simulate_season(schedule, after, fit, cfg, uniforms, offsets=offsets)
    out = {}
    for c in teams or CODES:
        out[c] = {"before": b["teams"][c], "after": a["teams"][c],
                  "win_change": round(a["teams"][c]["mean_wins"] - b["teams"][c]["mean_wins"], 1),
                  "strength_before": round(before[c], 2), "strength_after": round(after[c], 2)}
    return out


def simulate_trades(league, cba, trades, schedule, on_date=None, cfg=None, engine=None):
    """Check `trades` in order, apply the ones that work, and simulate 2026-27 before and
    after with the player-availability engine (tradesim.engine). Only teams in working
    trades change; draft picks and cash don't affect the simulation."""
    from tradesim.checker import check_trades_in_sequence
    from tradesim.engine import Engine
    cfg = cfg or load_sim_config()
    results, _ = check_trades_in_sequence(league, cba, trades, on_date)
    moves = [{"player": m["id"], "from": m["from"], "to": m["to"]}
             for trade, r in zip(trades, results) if r["works"]
             for m in trade["moves"] if m["type"] == "player"]
    engine = engine or Engine(league, schedule, cfg)
    out = engine.scenario(moves)
    out["checks"] = results
    return out


def season_table(league=None, cfg=None, engine=None):
    """2026-27 projection for every team from current rosters (player-availability engine)."""
    from tradesim.engine import Engine
    from tradesim.games import load_schedule_2026_27
    from tradesim.league import League
    league = league or League.load()
    cfg = cfg or load_sim_config()
    engine = engine or Engine(league, load_schedule_2026_27(), cfg)
    sim = engine.baseline()
    mean = sum(sim["mean_strength"].values()) / len(CODES)
    rows = [{"team": c, "conference": TEAM_INFO[c]["conference"], "strength": round(sim["mean_strength"][c] - mean, 1),
             **{k: sim["teams"][c][k] for k in ("mean_wins", "range", "playoff_pct", "play_in_pct")},
             "top_seed_pct": sim["teams"][c]["seed_frequency"][0]}
            for c in CODES]
    return sorted(rows, key=lambda r: -r["mean_wins"])


if __name__ == "__main__":
    from tradesim.report import terminal_summary, write_reports
    cfg = load_sim_config()
    table = season_table(cfg=cfg)
    paths = write_reports(table, "season_2026_27", "2026-27 season projection (current rosters)", notes=[
        f"{cfg['simulation']['n_seasons']:,} simulated seasons, seed {cfg['simulation']['seed']}, every team starts 0-0.",
        "Strength = expected net rating per 100 possessions vs an average team.",
        "Range = 10th to 90th percentile of simulated wins. Playoff = seeds 1-6, play-in = seeds 7-10.",
    ])
    print(terminal_summary(table))
    print("Full results:", *paths, sep="\n  ")
