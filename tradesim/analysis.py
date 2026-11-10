"""Team analysis for the trade simulator's team page (Stage 3).

Everything here comes from the simulator and the league data; no LLM. (Stage 5 adds an
LLM step that turns this into skill needs and trade suggestions.)

  projection  baseline 2026-27 simulation: average wins, 10-90% range, playoff / play-in /
              #1-seed odds, conference rank
  cap         team salary vs the cap, tax line and aprons; hard cap; standard contracts
  positions   for guards, forwards and centers: player impact weighted by expected minutes
              (injuries counted; a "G-F" splits his minutes), ranked 1-30
  needs       position groups in the bottom third of the league, the weakest regular
              rotation players, and long-term injuries
  roster      players by minutes in the full-strength rotation
"""
import json
import os
from functools import lru_cache

from tradesim.checker import cap_status
from tradesim.rotation import buckets
from tradesim.teams import TEAM_INFO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSITION_NAMES = {0: "Guards", 1: "Forwards", 2: "Centers"}
NEED_RANK = 21  # bottom third of 30


def expected_minutes(rotation):
    """Average minutes per game over a season, counting expected absences: his own minutes
    when available, plus what he picks up when teammates are out (tradesim.rotation)."""
    out = {pid: m * rotation.players[pid]["availability"] for pid, m in rotation.minutes.items()}
    for pid in rotation.players:
        missing = 1 - rotation.players[pid]["availability"]
        for k, gained in rotation.absence_transfer(pid).items():
            out[k] += missing * gained
    return out


def position_profile(rotation):
    """{bucket: {"minutes", "impact"}} using expected minutes (injuries counted); a player's
    minutes are split evenly across his position buckets ("G-F" = half guard, half forward)."""
    totals = {b: {"minutes": 0.0, "weighted": 0.0} for b in POSITION_NAMES}
    for pid, minutes in expected_minutes(rotation).items():
        if minutes <= 0:
            continue
        bs = buckets(rotation.players[pid]["position"])
        for b in bs:
            totals[b]["minutes"] += minutes / len(bs)
            totals[b]["weighted"] += minutes / len(bs) * rotation.players[pid]["impact"]
    return {b: {"minutes": t["minutes"], "impact": t["weighted"] / t["minutes"] if t["minutes"] else 0.0}
            for b, t in totals.items()}


@lru_cache(maxsize=1)
def _branding():
    with open(os.path.join(ROOT, "data", "team_branding.json")) as f:
        raw = json.load(f)
    return {TEAM_INFO_BY_SHORT[k]: v for k, v in raw.items() if not k.startswith("_")}


TEAM_INFO_BY_SHORT = {info["short"]: code for code, info in TEAM_INFO.items()}


def team_colors(code):
    b = _branding().get(code, {})
    return {"primary": b.get("primary", "#444444"), "secondary": b.get("secondary", "#888888")}


def teams_overview(engine):
    """All 30 teams by conference, with colors and the baseline projection."""
    base = engine.baseline()["teams"]
    out = {"East": [], "West": []}
    for code, info in TEAM_INFO.items():
        out[info["conference"]].append({"code": code, "name": info["name"], "colors": team_colors(code),
                                        "mean_wins": base[code]["mean_wins"],
                                        "playoff_pct": base[code]["playoff_pct"]})
    for conf in out:
        out[conf].sort(key=lambda t: t["name"])
    return out


def team_analysis(code, engine, league, cba):
    base = engine.baseline()["teams"]
    rotations = engine.baseline_rotations
    rotation = rotations[code]
    info = TEAM_INFO[code]
    t = base[code]
    season_end = max(g["date"] for g in engine.schedule if g["date"])
    conf_order = sorted((c for c in TEAM_INFO if TEAM_INFO[c]["conference"] == info["conference"]),
                        key=lambda c: -base[c]["mean_wins"])

    profiles = {c: position_profile(r) for c, r in rotations.items()}
    positions = []
    for b, name in POSITION_NAMES.items():
        ranking = sorted(TEAM_INFO, key=lambda c: -profiles[c][b]["impact"])
        rank = ranking.index(code) + 1
        league_avg = sum(profiles[c][b]["impact"] for c in TEAM_INFO) / len(TEAM_INFO)
        p = profiles[code][b]
        positions.append({"group": name, "minutes": round(p["minutes"], 1), "impact": round(p["impact"], 2),
                          "league_average": round(league_avg, 2), "rank": rank,
                          "verdict": "need" if rank >= NEED_RANK else ("strength" if rank <= 10 else "average")})

    roster = []
    rated = engine.ratings["players"]
    for b in rotation.breakdown():
        p, r = league.players[b["id"]], rated[b["id"]]
        roster.append({"id": b["id"], "name": b["name"], "position": b["position"], "age": r.get("age"),
                       "salary": p["salary"], "impact": round(b["impact"], 2), "minutes": b["minutes"],
                       "availability": round(r["availability"], 2),
                       "long_injury": bool(r.get("long_injury")),
                       "return_date": (r.get("long_injury") or {}).get("return_date")})

    rotation_players = [x for x in roster if x["minutes"] >= 15]
    weak_links = sorted(rotation_players, key=lambda x: x["impact"])[:2]
    needs = [p["group"] for p in sorted(positions, key=lambda p: -p["rank"]) if p["verdict"] == "need"]
    needs_type = "need"
    if not needs:  # no group in the bottom third: point at the relatively weakest one
        needs, needs_type = [max(positions, key=lambda p: p["rank"])["group"]], "relative"

    team = league.teams[code]
    salary = team["team_salary"]
    thresholds = {"salary_cap": cba["salary_cap"], "tax_line": cba["tax_line"],
                  "first_apron": cba["first_apron"], "second_apron": cba["second_apron"]}
    return {
        "code": code, "name": info["name"], "conference": info["conference"], "colors": team_colors(code),
        "projection": {"mean_wins": t["mean_wins"], "range_10_90": t["range"], "playoff_pct": t["playoff_pct"],
                       "play_in_pct": t["play_in_pct"], "top_seed_pct": t["top_seed_pct"],
                       "conference_rank": conf_order.index(code) + 1,
                       "mcse_wins": t["mcse"]["mean_wins"], "n_sims": engine.n_sims},
        "cap": {"team_salary": salary, "payroll": team["payroll"], "other_charges": team["other_cap_charges"],
                "status": cap_status(salary, cba), "thresholds": thresholds,
                "room": {k: v - salary for k, v in thresholds.items()},
                "hard_cap": team.get("hard_cap"), "hard_cap_reason": team.get("hard_cap_reason"),
                "standard_contracts": team["standard_contracts"]},
        "positions": positions,
        "needs": needs,
        "needs_type": needs_type,
        "weak_links": [{"name": w["name"], "position": w["position"], "impact": w["impact"], "minutes": w["minutes"]}
                       for w in weak_links],
        # out_for_season: expected back after the last regular-season game
        "long_injuries": [{"name": x["name"], "return_date": x["return_date"],
                           "out_for_season": bool(x["return_date"]) and x["return_date"] > season_end}
                          for x in roster if x["long_injury"]],
        "roster": roster,
    }


def data_status(league, cfg, today):
    """How old league.json's data is; stale = older than config data.max_age_days."""
    from datetime import date
    limit = cfg["data"]["max_age_days"]
    age = (today - date.fromisoformat(league.as_of)).days if league.as_of else None
    return {"as_of": league.as_of, "age_days": age, "max_age_days": limit,
            "stale": age is None or age > limit, "sources_as_of": league.sources_as_of}
