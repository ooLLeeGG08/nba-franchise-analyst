"""Check team strength forecasts against what happened, 2019-20 to 2025-26.

For each season, every team's net rating is predicted from what was known BEFORE
the season (player priors from earlier seasons + rho x last season's residual), then
compared with the actual net rating. Two minute models:
  actual minutes:    each player's real minutes that season (tests the ratings)
  projected minutes: last season's minutes per game played x expected share of
                     games played, as a 240-minute rotation (tests the
                     ratings + the minutes model, like a real projection)
The old method (last season's BPM only, shrunk 250 minutes toward -2.0) is shown
for comparison. The key number is the slope of actual on predicted: 1.0 means
projections are neither too extreme (< 1) nor too timid (> 1).

The prior's settings are fitted on these same seasons, so this is mildly in-sample;
Stage 7 adds a leave-one-season-out backtest.

Run:  python -m tradesim.strength_check
"""
import json
import os

import numpy as np

from tradesim.history import load_season, previous, team_ratings
from tradesim.model import load_sim_config, player_value
from tradesim.names import name_key
from tradesim.ratings import (FIT_PATH, _target_age, availability, draft_picks, history, load_fit,
                              prior_for, rotation_minutes)
from tradesim.teams import TEAM_INFO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_PATH = os.path.join(ROOT, "data", "model", "strength_check.json")


def _prior_impact(key, season, fit, cfg):
    hist = history(key, season, cfg["ratings"]["history_seasons"])
    draft = draft_picks().get(key)
    pick = draft[1] if draft and draft[0] <= int(season[:4]) else None
    totals = load_season(season)[0].get(key) or {}
    return prior_for(hist, totals.get("age") or _target_age(hist), pick, fit, cfg)[0], pick


def _old_impact(key, season, cfg):
    rec = load_season(previous(season))[0].get(key)
    return player_value(rec["bpm"], rec["mp"], cfg) if rec else cfg["player_value"]["replacement_bpm"]


def _prior_mpg(key, season, pick, fit, cfg):
    rec = load_season(previous(season))[0].get(key)
    if rec and rec.get("mp") and rec.get("g"):
        return rec["mp"] / max(rec["g"], cfg["minutes"]["games_floor"])
    rk = fit["rookies"]
    return max(rk["mpg_intercept"] + rk["mpg_per_log_pick"] * np.log(pick), 4.0) if pick else rk["undrafted_mpg"]


def forecasts(season, fit, cfg):
    """{team: {"actual", "new_actual_min", "new_projected_min", "old_actual_min"}} for one season."""
    _, stints = load_season(season)
    games = team_ratings()[season]
    rho = fit["team_residual"]["rho"]
    prev_resid = fit["team_residual"]["by_season"].get(previous(season), {})
    out = {code: {"actual": games[code]["net_rating"], "new_actual_min": 0.0, "old_actual_min": 0.0}
           for code in TEAM_INFO}
    first_team, info = {}, {}
    for s in stints:
        key = name_key(s["name"])
        impact, pick = _prior_impact(key, season, fit, cfg)
        info[key] = (impact, pick)
        share = (s["mp"] or 0) / (games[s["team"]]["games"] * 48)
        out[s["team"]]["new_actual_min"] += impact * share
        out[s["team"]]["old_actual_min"] += _old_impact(key, season, cfg) * share
        first_team.setdefault(key, s["team"])
    for code in TEAM_INFO:
        keys = [k for k, t in first_team.items() if t == code]
        mpgs = {k: _prior_mpg(k, season, info[k][1], fit, cfg) * availability(k, season, fit, cfg) for k in keys}
        minutes = rotation_minutes(mpgs, cfg["minutes"]["team_minutes"], cfg["ratings"]["max_mpg"])
        out[code]["new_projected_min"] = sum(info[k][0] * minutes[k] / 48 for k in keys)
        for field in ("new_actual_min", "new_projected_min"):
            out[code][field] += rho * prev_resid.get(code, 0.0)
    return out


def _summary(pred, actual):
    pred, actual = np.array(pred), np.array(actual)
    centred = pred - pred.mean()
    slope = float(np.sum(centred * (actual - actual.mean())) / np.sum(centred ** 2))
    return {"slope": round(slope, 2), "mae": round(float(np.mean(np.abs(pred - actual))), 2),
            "rmse": round(float(np.sqrt(np.mean((pred - actual) ** 2))), 2),
            "corr": round(float(np.corrcoef(pred, actual)[0, 1]), 2)}


def run(cfg=None, write=True):
    cfg = cfg or load_sim_config()
    fit = load_fit()
    seasons = cfg["ratings"]["fit_target_seasons"]
    rows = {s: forecasts(s, fit, cfg) for s in seasons}
    report = {"seasons": seasons, "pooled": {}, "by_season": {}}
    methods = {"new_projected_min": "new ratings, projected minutes",
               "new_actual_min": "new ratings, actual minutes",
               "old_actual_min": "old method, actual minutes"}
    for field in methods:
        pred = [rows[s][c][field] - np.mean([rows[s][t][field] for t in TEAM_INFO]) for s in seasons for c in TEAM_INFO]
        actual = [rows[s][c]["actual"] for s in seasons for c in TEAM_INFO]
        report["pooled"][field] = _summary(pred, actual)
    for s in seasons:
        report["by_season"][s] = {f: _summary([rows[s][c][f] for c in TEAM_INFO], [rows[s][c]["actual"] for c in TEAM_INFO])
                                  for f in methods}
    # Latent strength uncertainty for the simulator: the forecast error against OBSERVED season
    # net ratings, minus the game-to-game luck in those observed ratings. Luck per team-season =
    # sigma / sqrt(games), with sigma the fitted single-game spread (tradesim.game_model); short
    # seasons (2019-20, 2020-21) have more luck.
    from tradesim.game_model import load_model
    sigma = load_model()["sigma"]
    games = team_ratings()
    errors = []
    for s in seasons:
        mean_pred = np.mean([rows[s][t]["new_projected_min"] for t in TEAM_INFO])
        for c in TEAM_INFO:
            errors.append({"season": s, "team": c, "predicted": round(rows[s][c]["new_projected_min"] - mean_pred, 3),
                           "actual": rows[s][c]["actual"], "games": games[s][c]["games"]})
    err2 = np.mean([(e["predicted"] - e["actual"]) ** 2 for e in errors])
    luck2 = np.mean([sigma ** 2 / e["games"] for e in errors])
    report["forecast_rmse"] = round(float(np.sqrt(err2)), 3)
    report["game_luck_sd"] = round(float(np.sqrt(luck2)), 3)
    report["strength_sd"] = round(float(np.sqrt(max(err2 - luck2, 0))), 3)
    # First version subtracted 1.70 points of luck estimated from single-game margin spread,
    # which also contains opponent and home/away differences; kept for reference.
    old_luck = _net_rating_luck()
    report["strength_sd_first_version"] = round(float(np.sqrt(max(err2 - old_luck ** 2, 0))), 3)
    report["team_season_errors"] = errors
    if write:
        with open(CHECK_PATH, "w") as f:
            json.dump(report, f, indent=1)
    return report, methods


def _net_rating_luck():
    """Spread of a full-season net rating from game-to-game luck alone: the spread of single-game
    margins around each team's average, divided by sqrt(82) (2025-26 games)."""
    from tradesim.games import load_results_2025_26
    margins = {}
    for g in load_results_2025_26():
        m = g["home_pts"] - g["away_pts"]
        margins.setdefault(g["home"], []).append(m)
        margins.setdefault(g["away"], []).append(-m)
    within = np.sqrt(np.mean([np.var(v, ddof=1) for v in margins.values()]))
    return float(within / np.sqrt(82))


if __name__ == "__main__":
    r, methods = run()
    print("Predicting each team's net rating before the season, 2019-20 to 2025-26 (210 team-seasons):")
    for field, label in methods.items():
        p = r["pooled"][field]
        print(f"  {label:32s} slope {p['slope']:.2f}  avg error {p['mae']:.2f} pts  corr {p['corr']:.2f}")
    print(f"Forecast error vs observed net rating: {r['forecast_rmse']} points; game luck in those ratings "
          f"{r['game_luck_sd']} (sigma / sqrt(games)) -> latent strength uncertainty {r['strength_sd']} points "
          f"(first version: {r['strength_sd_first_version']})")
    print(f"Wrote {CHECK_PATH}")
