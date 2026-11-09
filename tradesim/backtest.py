"""Backtest the full pipeline on 2025-26: predicted vs actual wins.

In-sample (2025-26 stats predicting 2025-26 wins; checks the mechanics):
  A. Actual minutes: each player's real minutes with each team.
  B. Projected minutes: the same players, minutes from the allocation rule.

Forecast (only 2024-25 stats; the honest test of predicting a new season):
  C. 2024-25 player values x actual 2025-26 minutes. Tests how well last
     season's BPM carries over, with the rotation known.
  D. Full forecast: 2024-25 values AND minutes from the allocation rule, for
     each player's first 2025-26 team. This is how 2026-27 is projected.
     (It still knows who ended up playing for each team, so it's a little
     easier than a true opening-night forecast.)

The win model's two constants are fitted on 2025-26 games in all versions.

Run:  python -m tradesim.backtest
"""
import json
import os

import numpy as np

from tradesim import build_data
from tradesim.fit import FIT_PATH, fit as run_fit, load_fit, strengths_2025_26
from tradesim.games import GAMES_PER_TEAM, actual_wins, load_results_2025_26, schedule_from_results
from tradesim.model import allocate_minutes, load_sim_config, player_value
from tradesim.names import name_key
from tradesim.simulate import simulate_season
from tradesim.teams import TEAM_INFO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKTEST_PATH = os.path.join(ROOT, "data", "model", "backtest_2025_26.json")


def strengths_projected_minutes(cfg):
    """Each team's 2025-26 players, with minutes from the allocation rule instead of real minutes."""
    repl = cfg["player_value"]["replacement_bpm"]
    floor = cfg["minutes"]["games_floor"]
    stints = build_data.parse_bbref_stints(build_data._read("bbref_advanced_2025_26.tsv"))
    out = {}
    for code in TEAM_INFO:
        team = [s for s in stints if s["team"] == code and s["mp"]]
        mpgs = {s["name"]: s["mp"] / max(s["g"], floor) for s in team}
        minutes = allocate_minutes(mpgs, cfg)
        out[code] = sum((player_value(s["bpm"], s["mp"], cfg) - repl) * minutes[s["name"]] / 48 for s in team)
    return out


def _values_2024_25(cfg):
    prev = build_data.parse_bbref(build_data._read_raw("2024_25", "bbref_advanced_2024_25.txt"))
    return {key: (player_value(st["bpm"], st["mp"], cfg), st["mp"] / max(st["g"], cfg["minutes"]["games_floor"]))
            for key, st in prev.items() if st.get("mp") and st.get("g")}


def strengths_forecast_actual_minutes(cfg):
    """C: 2024-25 player values, weighted by actual 2025-26 minutes with each team."""
    repl = cfg["player_value"]["replacement_bpm"]
    prev = _values_2024_25(cfg)
    stints = build_data.parse_bbref_stints(build_data._read("bbref_advanced_2025_26.tsv"))
    out = {code: 0.0 for code in TEAM_INFO}
    for s in stints:
        value = prev.get(name_key(s["name"]), (repl, None))[0]
        out[s["team"]] += (value - repl) * (s["mp"] or 0) / (GAMES_PER_TEAM * 48)
    return out


def strengths_forecast(cfg):
    """D: 2024-25 values and 2024-25 minutes per game, minutes allocated by the same rule
    as 2026-27, for each player's first 2025-26 team (Basketball-Reference lists stints
    in order). Players with no 2024-25 stats (mostly rookies) get replacement value and
    default minutes."""
    repl = cfg["player_value"]["replacement_bpm"]
    prev = _values_2024_25(cfg)
    stints = build_data.parse_bbref_stints(build_data._read("bbref_advanced_2025_26.tsv"))
    first_team = {}
    for s in stints:
        first_team.setdefault(name_key(s["name"]), s["team"])
    out = {}
    for code in TEAM_INFO:
        keys = [k for k, team in first_team.items() if team == code]
        mpgs = {k: prev[k][1] if k in prev else cfg["minutes"]["no_stats_mpg"]["other"] for k in keys}
        minutes = allocate_minutes(mpgs, cfg)
        out[code] = sum((prev.get(k, (repl, None))[0] - repl) * minutes[k] / 48 for k in keys)
    return out


def _errors(predicted, actual):
    diff = np.array([predicted[c] - actual[c] for c in TEAM_INFO])
    return {"mae": round(float(np.mean(np.abs(diff))), 2),
            "rmse": round(float(np.sqrt(np.mean(diff ** 2))), 2),
            "max_error": round(float(np.max(np.abs(diff))), 1),
            "within_5_wins": int(np.sum(np.abs(diff) <= 5))}


def run(cfg=None, write=True):
    cfg = cfg or load_sim_config()
    fit = load_fit() if os.path.exists(FIT_PATH) else run_fit(cfg, write=False)
    results = load_results_2025_26()
    schedule = schedule_from_results(results)
    actual = actual_wins(results)
    versions = {"A_actual_minutes": strengths_2025_26(cfg), "B_projected_minutes": strengths_projected_minutes(cfg),
                "C_forecast_actual_minutes": strengths_forecast_actual_minutes(cfg),
                "D_forecast": strengths_forecast(cfg)}
    report = {"season": "2025-26", "fit": {"home": fit["home"], "slope": fit["slope"]},
              "naive_41_wins": _errors({c: 41 for c in TEAM_INFO}, actual), "versions": {}}
    for name, strengths in versions.items():
        sim = simulate_season(schedule, strengths, fit, cfg)
        predicted = {c: sim["teams"][c]["mean_wins"] for c in TEAM_INFO}
        in_range = sum(1 for c in TEAM_INFO
                       if sim["teams"][c]["range"][0] <= actual[c] <= sim["teams"][c]["range"][1])
        report["versions"][name] = {
            "in_sample": name[0] in "AB",
            **_errors(predicted, actual),
            "actual_inside_10_90_range": in_range,
            "teams": {c: {"actual": actual[c], "predicted": predicted[c], "range": sim["teams"][c]["range"]}
                      for c in sorted(TEAM_INFO, key=lambda c: -actual[c])},
        }
    report["strength_uncertainty"] = _strength_uncertainty(report["versions"]["D_forecast"], fit)
    if write:
        os.makedirs(os.path.dirname(BACKTEST_PATH), exist_ok=True)
        with open(BACKTEST_PATH, "w") as f:
            json.dump(report, f, indent=1)
    return report


def _strength_uncertainty(version, fit):
    """How much of the forecast error is NOT game-to-game luck.

    Forecast misses come from two sources: luck in 82 coin flips (spread of about
    sqrt(82 x 0.25) = 4.5 wins) and not knowing how good a team really is. Removing
    the luck part from the observed spread leaves the second, converted to strength
    points with the win model's slope (one point of strength is worth about
    82 x slope / 4 wins for an average team)."""
    diffs = [t["actual"] - t["predicted"] for t in version["teams"].values()]
    observed = float(np.sqrt(np.mean(np.square(diffs))))
    luck = float(np.sqrt(82 * 0.25))
    extra_wins = float(np.sqrt(max(observed ** 2 - luck ** 2, 0)))
    wins_per_point = 82 * fit["slope"] / 4
    return {"observed_rmse_wins": round(observed, 2), "luck_wins": round(luck, 2),
            "extra_wins": round(extra_wins, 2), "strength_sd_points": round(extra_wins / wins_per_point, 2)}


if __name__ == "__main__":
    r = run()
    print(f"Naive guess (41 wins each): average error {r['naive_41_wins']['mae']} wins")
    for name, v in r["versions"].items():
        print(f"{name}{' (in-sample)' if v['in_sample'] else ''}: average error {v['mae']} wins, RMSE {v['rmse']}, worst {v['max_error']}, "
              f"{v['within_5_wins']}/30 within 5 wins, {v['actual_inside_10_90_range']}/30 inside the 10-90% range")
    u = r["strength_uncertainty"]
    print(f"Forecast spread {u['observed_rmse_wins']} wins = luck {u['luck_wins']} + team-strength uncertainty "
          f"{u['extra_wins']} wins (about {u['strength_sd_points']} points of strength)")
    print(f"Wrote {BACKTEST_PATH}")
