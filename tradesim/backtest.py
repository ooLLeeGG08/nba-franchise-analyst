"""Backtest the full pipeline on 2025-26: predicted vs actual wins.

Two versions:
  A. Actual minutes: each player's real minutes with each team.
     Tests steps 2-3 (win probability + season simulation).
  B. Projected minutes: the same players, but minutes come from the
     allocation rule used for 2026-27 and for trades. Tests steps 1-3.

Both are IN-SAMPLE: 2025-26 stats are used to predict 2025-26 wins, so this
checks that the pipeline turns player stats into wins correctly, not how well
it forecasts a season ahead. A true forecast test needs 2024-25 stats.

Run:  python -m tradesim.backtest
"""
import json
import os

import numpy as np

from tradesim import build_data
from tradesim.fit import FIT_PATH, fit as run_fit, load_fit, strengths_2025_26
from tradesim.games import actual_wins, load_results_2025_26, schedule_from_results
from tradesim.model import allocate_minutes, load_sim_config, player_value
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
    versions = {"A_actual_minutes": strengths_2025_26(cfg), "B_projected_minutes": strengths_projected_minutes(cfg)}
    report = {"season": "2025-26", "in_sample": True, "fit": {"home": fit["home"], "slope": fit["slope"]},
              "naive_41_wins": _errors({c: 41 for c in TEAM_INFO}, actual), "versions": {}}
    for name, strengths in versions.items():
        sim = simulate_season(schedule, strengths, fit, cfg)
        predicted = {c: sim["teams"][c]["mean_wins"] for c in TEAM_INFO}
        in_range = sum(1 for c in TEAM_INFO
                       if sim["teams"][c]["range"][0] <= actual[c] <= sim["teams"][c]["range"][1])
        report["versions"][name] = {
            **_errors(predicted, actual),
            "actual_inside_10_90_range": in_range,
            "teams": {c: {"actual": actual[c], "predicted": predicted[c], "range": sim["teams"][c]["range"]}
                      for c in sorted(TEAM_INFO, key=lambda c: -actual[c])},
        }
    if write:
        os.makedirs(os.path.dirname(BACKTEST_PATH), exist_ok=True)
        with open(BACKTEST_PATH, "w") as f:
            json.dump(report, f, indent=1)
    return report


if __name__ == "__main__":
    r = run()
    print(f"Naive guess (41 wins each): average error {r['naive_41_wins']['mae']} wins")
    for name, v in r["versions"].items():
        print(f"{name}: average error {v['mae']} wins, RMSE {v['rmse']}, worst {v['max_error']}, "
              f"{v['within_5_wins']}/30 within 5 wins, {v['actual_inside_10_90_range']}/30 inside the 10-90% range")
    print(f"Wrote {BACKTEST_PATH}")
