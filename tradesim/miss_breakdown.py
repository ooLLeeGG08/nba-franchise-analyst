"""Why did the model miss a season? Per-team breakdown of the model's error vs Vegas.

For each team, the model's Nov 9 forecast is compared with what happened, and the miss is
split into measurable parts (in points of net rating, about 2.7 wins each over a season):
  rating    players on the Nov 9 roster played better/worse than their prior rating
            (their actual BPM vs prior, weighted by the minutes they actually played)
  rookies   the same, for players with no NBA history (rookie prior by draft slot)
  injuries  players on the Nov 9 roster who missed more games than expected
            (games short of expectation x their prior impact above replacement)
  turnover  share of the team's minutes played by players who joined after Nov 9
Run:  python -m tradesim.miss_breakdown 2025-26
"""
import json
import sys

import numpy as np

from tradesim import backtest_nov9 as bt
from tradesim import ratings as rt
from tradesim.history import load_season, team_ratings
from tradesim.model import load_sim_config


def breakdown(season, top=5):
    cfg = load_sim_config()
    with open(bt.OUT_PATH) as f:
        report = json.load(f)
    rows = {r["team"]: r for r in report["vegas"]["rows"] if r["season"] == season}
    fold_cfg = {**cfg, "ratings": {**cfg["ratings"], "fit_target_seasons":
                                   [s for s in cfg["ratings"]["fit_target_seasons"] if s != season]}}
    fit = rt.fit(fold_cfg, write=False)
    league, rated, _ = bt.build_season(season, fit, cfg)
    _, stints = load_season(season)
    games = team_ratings()[season]
    repl = cfg["player_value"]["replacement_bpm"]
    out = []
    for code, r in rows.items():
        roster = {pid: p for pid, p in league.players.items() if p["team"] == code}
        roster_keys = {p["bbref_id"]: pid for pid, p in roster.items() if p.get("bbref_id")}
        team_stints = [s for s in stints if s["team"] == code and s.get("mp")]
        g, total_mp = games[code]["games"], sum(s["mp"] for s in team_stints)
        rating = rookie = 0.0
        newcomers = []
        for s in team_stints:
            key = s["bbref_id"]
            share = s["mp"] / (g * 48)
            if key in roster_keys:
                pid = roster_keys[key]
                miss = ((s["bpm"] if s["bpm"] is not None else rated["players"][pid]["impact"])
                        - rated["players"][pid]["impact"]) * share
                if rt.history(key, season, 3):
                    rating += miss
                else:
                    rookie += miss
            else:
                newcomers.append((s["name"], s["mp"]))
        injuries, injured = 0.0, []
        for pid, p in roster.items():
            info = rated["players"][pid]
            played = sum(s["g"] for s in team_stints if s["bbref_id"] == p.get("bbref_id"))
            expected = info["availability"] * 82
            short = expected - played
            if short > 8 and info["mpg_when_playing"] >= 20:
                cost = short / 82 * (info["impact"] - repl) * info["mpg_when_playing"] / 48
                injuries -= cost
                injured.append(f"{p['name']} {played} of ~{expected:.0f} games")
        turnover = sum(mp for _, mp in newcomers) / total_mp if total_mp else 0.0
        actual_net = games[code]["net_rating"]
        out.append({
            "team": code, "actual": r["actual_wins"], "model": round(r["predicted_wins"], 1),
            "vegas": round(r["vegas_wins"], 1),
            "model_error": round(abs(r["predicted_wins"] - r["actual_wins"]), 1),
            "vegas_error": round(abs(r["vegas_wins"] - r["actual_wins"]), 1),
            "worse_than_vegas_by": round(abs(r["predicted_wins"] - r["actual_wins"])
                                         - abs(r["vegas_wins"] - r["actual_wins"]), 1),
            "actual_net_rating": actual_net,
            "parts_points": {"rating": round(rating, 2), "rookies": round(rookie, 2), "injuries": round(injuries, 2)},
            "turnover_minutes_share": round(turnover, 2),
            "top_newcomers": [n for n, _ in sorted(newcomers, key=lambda x: -x[1])[:3]],
            "injured": injured[:3],
            "rating_misses": _top_rating_misses(code, team_stints, roster_keys, rated, g),
        })
    out.sort(key=lambda x: -x["worse_than_vegas_by"])
    return out[:top]


def _top_rating_misses(code, team_stints, roster_keys, rated, g):
    misses = []
    for s in team_stints:
        pid = roster_keys.get(s["bbref_id"])
        if pid and s["bpm"] is not None:
            prior = rated["players"][pid]["impact"]
            misses.append((s["name"], round(prior, 1), s["bpm"], (s["bpm"] - prior) * s["mp"] / (g * 48)))
    misses.sort(key=lambda m: -abs(m[3]))
    return [f"{n}: prior {p:+.1f}, actual {a:+.1f}" for n, p, a, _ in misses[:3]]


if __name__ == "__main__":
    season = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
    for t in breakdown(season):
        print(json.dumps(t, ensure_ascii=False))
