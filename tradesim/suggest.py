"""Trade suggestions (Stage 5): LLM needs -> code search -> cap check -> simulation.

  1. Needs: tradesim.ai.team_needs (positions + skills from fixed lists; data fallback).
  2. Candidates: players on other teams who play a needed position, are at least the 55th
     percentile in the needed skills (tradesim.skills), and are an upgrade of 0.75+ impact on
     the team's weakest regular at that position. Skipped: no-trade clause or veto rights,
     signed this summer and not yet tradeable, long-term injured, under 18 minutes a game.
  3. Packages: 1-3 outgoing players from the team (never its top 3 by contribution), keeping
     both rosters at 14-15 and passing a quick salary-matching test for both teams; the
     package giving up the least talent wins. Bigger upgrades add a sweetener pick (a value
     heuristic, not a fairness check): +1.0 impact -> the team's latest own 2nd, +2.0 -> its
     latest own 1st. Every package then goes through the full cap checker.
  4. Ranking: a quick strength screen (expected strength change) keeps the best legal trades
     (one per incoming player, at most 2 per partner); each is simulated with the season engine
     and the top 4 by win gain are returned. Realism rule (config "suggestions", not a cap rule):
     trades costing the partner more than 1.5 projected wins, or adding under 0.5 wins for the
     team, are dropped. Without it the "best legal trade" is a heist (a superstar for a role
     player), which the cap rules allow but no team would accept.
  5. Explanations: tradesim.ai.explain (name- and number-checked; template fallback).

Every player named comes from the database: candidates are database players, and LLM text is
checked against the names in that trade.
"""
import hashlib
import json
import os
from itertools import combinations

from tradesim import ai
from tradesim.analysis import expected_minutes, team_analysis
from tradesim.checker import _matching, check_trade
from tradesim.picks import label as pick_label
from tradesim.rotation import apply_moves, buckets
from tradesim.skills import player_skills, team_skills
from tradesim.trade_api import _tradeable_from

SUGGEST_VERSION = "stage5-2"
BUCKET_OF = {"G": 0, "F": 1, "C": 2}
MIN_SKILL_FIT = 55
MIN_UPGRADE = 0.75
MIN_MPG = 18
N_CANDIDATES = 60
N_SIMULATE = 8
WINS_PER_POINT = 2.6  # quick screen only; the final numbers come from the simulation


def team_facts(code, engine, league, cba):
    """What the LLM sees: numbers only, no player names."""
    a = team_analysis(code, engine, league, cba)
    rotation = engine.baseline_rotations[code]
    return {
        "team": code, "team_name": a["name"],
        "projection": {k: a["projection"][k] for k in ("mean_wins", "playoff_pct", "conference_rank")},
        "positions": [{k: p[k] for k in ("group", "rank", "impact", "league_average")} for p in a["positions"]],
        "needs": a["needs"],
        "team_skills": team_skills(rotation, league, expected_minutes(rotation)),
        "cap": {"status": a["cap"]["status"], "room_to_first_apron_m": round(a["cap"]["room"]["first_apron"] / 1e6, 1),
                "hard_cap": a["cap"]["hard_cap"]},
        "rotation_ages": sorted(round(r["age"]) for r in a["roster"] if r["minutes"] >= 15 and r.get("age")),
    }


def _restricted(player, cba, on_date):
    if player.get("no_trade_clause") or player.get("bird_veto"):
        return True
    when = _tradeable_from(player, cba)
    return bool(when and on_date.isoformat() < when)


def _contribution(rotation, pid, em):
    return rotation.players[pid]["impact"] * em.get(pid, 0) / 48


def find_candidates(code, needs, engine, league, cba, on_date):
    rotation = engine.baseline_rotations[code]
    em = expected_minutes(rotation)
    rated = engine.ratings["players"]
    wanted = {BUCKET_OF[p] for p in needs["positions"]}
    weakest = {}
    for pid, minutes in em.items():
        if minutes >= 12:
            for b in buckets(rotation.players[pid]["position"]):
                weakest[b] = min(weakest.get(b, 99), rotation.players[pid]["impact"])
    out = []
    for pid, p in league.players.items():
        if p["team"] == code or not p["on_roster"] or _restricted(p, cba, on_date):
            continue
        r = rated[pid]
        if r.get("long_injury") or r["availability"] < 0.5 or r["mpg_when_playing"] < MIN_MPG:
            continue
        overlap = buckets(p.get("position")) & wanted
        if not overlap:
            continue
        skills = player_skills(p)
        fit = sum(skills.get(s, 0) for s in needs["skills"]) / len(needs["skills"])
        upgrade = r["impact"] - min(weakest.get(b, 0) for b in overlap)
        if fit < MIN_SKILL_FIT or upgrade < MIN_UPGRADE:
            continue
        out.append({"id": pid, "team": p["team"], "salary": p["salary"], "impact": r["impact"], "upgrade": upgrade,
                    "fit": fit, "score": upgrade * min(r["mpg_when_playing"], 34) / 48 + 0.02 * fit})
    out.sort(key=lambda c: -c["score"])
    return out[:N_CANDIDATES]


def _packages(code, cand, engine, league, cba, on_date):
    """Outgoing player combinations for one candidate, best (least talent given up) first."""
    rotation = engine.baseline_rotations[code]
    em = expected_minutes(rotation)
    core = set(sorted(rotation.players, key=lambda pid: -_contribution(rotation, pid, em))[:3])
    pool = [p for p in league.roster(code) if p["id"] not in core and not _restricted(p, cba, on_date)]
    team, partner = league.teams[code], league.teams[cand["team"]]
    n, m = team["standard_contracts"], partner["standard_contracts"]
    lo, hi = cba["roster"]["min_standard"], cba["roster"]["max_standard"]
    found = []
    for k in (1, 2, 3):
        if not (lo <= n - k + 1 <= hi and lo <= m - 1 + k <= hi):
            continue
        for combo in combinations(pool, k):
            out_sal = sum(p["salary"] for p in combo)
            t_after = team["team_salary"] - out_sal + cand["salary"]
            p_after = partner["team_salary"] - cand["salary"] + out_sal
            if not _matching(team["team_salary"], t_after, out_sal, cand["salary"], cba)[0]:
                continue
            if not _matching(partner["team_salary"], p_after, cand["salary"], out_sal, cba)[0]:
                continue
            given = sum(max(_contribution(rotation, p["id"], em), 0) for p in combo)
            found.append((given, k, combo))
    found.sort(key=lambda x: (x[0], x[1]))
    return [combo for _, _, combo in found[:3]]


def _sweetener(code, upgrade, league):
    """Latest own pick as a value sweetener: a 1st for +2.0 impact, a 2nd for +1.0."""
    rnd = 1 if upgrade >= 2.0 else (2 if upgrade >= 1.0 else None)
    if rnd is None:
        return None
    own = [p for p in league.picks_held(code) if p["kind"] == "own" and p["round"] == rnd]
    return max(own, key=lambda p: p["year"]) if own else None


def legal_trades(code, candidates, engine, league, cba, on_date):
    trades = []
    for cand in candidates:
        for combo in _packages(code, cand, engine, league, cba, on_date):
            moves = [{"type": "player", "id": cand["id"], "from": cand["team"], "to": code}]
            moves += [{"type": "player", "id": p["id"], "from": code, "to": cand["team"]} for p in combo]
            sweet = _sweetener(code, cand["upgrade"], league)
            options = ([moves + [{"type": "pick", "id": sweet["id"], "from": code, "to": cand["team"]}]] if sweet else []) + [moves]
            for option in options:
                result = check_trade(league, cba, {"moves": option}, on_date)
                if result["works"]:
                    trades.append({"candidate": cand, "moves": option, "check": result})
                    break
            else:
                continue
            break  # first legal package for this candidate
    return trades


def _quick_gain(code, trade, engine, league, cfg):
    """Expected-strength change (points) for the team and for the partner."""
    moves = [{"player": m["id"], "from": m["from"], "to": m["to"]} for m in trade["moves"] if m["type"] == "player"]
    after = apply_moves(league, moves, cfg, engine.ratings)
    partner = trade["candidate"]["team"]
    base = engine.baseline_rotations
    return (after[code].expected_strength() - base[code].expected_strength(),
            after[partner].expected_strength() - base[partner].expected_strength())


def _player_card(pid, league, engine):
    p, r = league.players[pid], engine.ratings["players"][pid]
    return {"id": pid, "name": p["name"], "position": p.get("position"), "salary": p["salary"],
            "salary_m": round(p["salary"] / 1e6, 1), "impact": round(r["impact"], 1), "age": r.get("age"),
            "team": p["team"]}


def suggest(code, engine, league, cba, on_date, llm=None, index=None, n=None, max_partner_loss="config"):
    """max_partner_loss: drop trades that cost the partner more than this many wins (quick screen
    first, then the simulated number); None = no limit. Defaults come from config/sim.json."""
    sc = engine.cfg.get("suggestions", {})
    n = n or sc.get("count", 4)
    if max_partner_loss == "config":
        max_partner_loss = sc.get("max_partner_loss_wins")
    min_gain = sc.get("min_win_gain", 0.0)
    index = index or ai.NameIndex(league.players)
    facts = team_facts(code, engine, league, cba)
    needs = ai.team_needs(facts, index, llm)
    candidates = find_candidates(code, needs, engine, league, cba, on_date)
    trades = legal_trades(code, candidates, engine, league, cba, on_date)
    for t in trades:
        t["quick"], t["partner_quick"] = _quick_gain(code, t, engine, league, engine.cfg)
    if max_partner_loss is not None:
        trades = [t for t in trades if t["partner_quick"] * WINS_PER_POINT >= -max_partner_loss * 1.5]
    trades.sort(key=lambda t: -t["quick"])
    shortlist, per_partner = [], {}
    for t in trades:
        partner = t["candidate"]["team"]
        if per_partner.get(partner, 0) >= 2:
            continue
        shortlist.append(t)
        per_partner[partner] = per_partner.get(partner, 0) + 1
        if len(shortlist) >= N_SIMULATE:
            break
    for t in shortlist:
        moves = [{"player": m["id"], "from": m["from"], "to": m["to"]} for m in t["moves"] if m["type"] == "player"]
        t["sim"] = engine.scenario(moves)
    if max_partner_loss is not None:
        shortlist = [t for t in shortlist
                     if t["sim"]["teams"][t["candidate"]["team"]]["delta"]["mean_wins"]["change"] >= -max_partner_loss]
    shortlist = [t for t in shortlist if t["sim"]["teams"][code]["delta"]["mean_wins"]["change"] >= min_gain]
    shortlist.sort(key=lambda t: -t["sim"]["teams"][code]["delta"]["mean_wins"]["change"])
    chosen = shortlist[:n]
    facts_sheets, cards = [], []
    for rank, t in enumerate(chosen, 1):
        partner = t["candidate"]["team"]
        sim_team, sim_partner = t["sim"]["teams"][code], t["sim"]["teams"][partner]
        d = sim_team["delta"]
        gets = [_player_card(m["id"], league, engine) for m in t["moves"] if m["type"] == "player" and m["to"] == code]
        sends = [_player_card(m["id"], league, engine) for m in t["moves"] if m["type"] == "player" and m["from"] == code]
        picks = [league.picks[m["id"]] for m in t["moves"] if m["type"] == "pick"]
        cand_skills = player_skills(league.players[t["candidate"]["id"]])
        chk = t["check"]["teams"]
        card = {
            "rank": rank, "partner": partner, "moves": t["moves"], "gets": gets, "sends": sends,
            "picks_out": [{"id": pk["id"], "label": pick_label(pk), "year": pk["year"]} for pk in picks],
            "cap": {"works": True,
                    "team": {k: chk[code][k] for k in ("salary_before", "salary_after", "status_before", "status_after")},
                    "partner": {k: chk[partner][k] for k in ("salary_before", "salary_after", "status_before", "status_after")},
                    "exception_used": chk[code].get("exception_used"),
                    "not_checked": sum(1 for team in chk.values() for r in team["rules"] if r["status"] == "not_checked")},
            "wins_before": sim_team["before"]["mean_wins"], "wins_after": sim_team["after"]["mean_wins"],
            "win_change": round(d["mean_wins"]["change"], 1), "win_change_mcse": d["mean_wins"]["mcse"],
            "win_change_80": [round(d["mean_wins"]["p10"]), round(d["mean_wins"]["p90"])],
            "playoff_before": sim_team["before"]["playoff_pct"], "playoff_after": sim_team["after"]["playoff_pct"],
            "partner_win_change": round(sim_partner["delta"]["mean_wins"]["change"], 1),
            "needs_addressed": {"positions": sorted({ai.POSITIONS[g] for g, b in BUCKET_OF.items()
                                                     if b in buckets(gets[0]["position"]) and g in needs["positions"]}),
                                "skills": {s: cand_skills.get(s) for s in needs["skills"]}},
        }
        cards.append(card)
        facts_sheets.append({
            "team": code, "gets": [{k: g[k] for k in ("id", "name", "position", "impact", "salary_m")} for g in gets],
            "sends": [{k: s[k] for k in ("id", "name", "position", "impact", "salary_m")} for s in sends],
            "picks": [{"label": p["label"], "year": p["year"]} for p in card["picks_out"]],
            "wins_before": round(card["wins_before"], 1), "wins_after": round(card["wins_after"], 1),
            "win_change": card["win_change"], "playoff_before": round(card["playoff_before"] * 100),
            "playoff_after": round(card["playoff_after"] * 100),
            "playoff_change": round((card["playoff_after"] - card["playoff_before"]) * 100),
            "skills_needed": needs["skills"],
        })
    for card, text in zip(cards, ai.explain(facts_sheets, index, llm)):
        card["explanation"] = text
    return {"team": code, "needs": needs, "suggestions": cards, "n_sims": engine.n_sims,
            "rules": {"max_partner_loss_wins": max_partner_loss, "min_win_gain": min_gain},
            "searched": {"candidates": len(candidates), "legal_trades": len(trades), "simulated": len(shortlist)}}


# --- caching ---------------------------------------------------------------------------------------

def cache_path(code, engine, model_name):
    from tradesim.engine import CACHE_DIR, fingerprint
    key = hashlib.sha256(f"{SUGGEST_VERSION}:{model_name}:{fingerprint(engine.n_sims, engine.seed, engine.schedule)}"
                         .encode()).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"suggestions_{code}_{key}.json")


def cached_suggest(code, engine, league, cba, on_date, llm=None, index=None):
    """Suggestions are slow (several simulations), so they're cached per team and inputs."""
    model_name = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b") if llm else "no-llm"
    path = cache_path(code, engine, model_name) + f".{on_date.isoformat()}"
    if os.path.exists(path):
        with open(path) as f:
            return {**json.load(f), "from_cache": True}
    result = suggest(code, engine, league, cba, on_date, llm, index)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(result, f)
    return {**result, "from_cache": False}
