"""Trade suggestions (Stage 5): LLM needs -> code search -> cap check -> simulation.

  1. Needs: tradesim.ai.team_needs (positions + skills from fixed lists; data fallback).
  2. Candidates: players on other teams who play a needed position, are at least the 55th
     percentile in the needed skills (tradesim.skills), and are an upgrade of 0.75+ impact on
     the team's weakest regular at that position. Skipped: no-trade clause or veto rights,
     signed this summer and not yet tradeable, long-term injured, under 18 minutes a game.
  3. Packages: every 1-3 player package from the team (never its top 3 by contribution) that
     keeps both rosters at 14-15 and passes a quick salary-matching test for both teams gets a
     quick strength check for BOTH teams; the package that helps the team most while costing
     the partner at most the realism limit wins. (Picking the package that gives up the least
     talent instead hurt the partner most, so nothing passed the realism rule.) Bigger
     upgrades add a sweetener pick (a value heuristic, not a fairness check): +1.0 impact ->
     the team's latest own 2nd, +2.0 -> its latest own 1st. Every package then goes through
     the full cap checker.
     If fewer than 4 trades come out, the search widens step by step: a lower skill bar, then
     the next-weakest position too, then the best available upgrade at any position. Each
     suggestion says how closely it matches the need.
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
import copy
import glob
import hashlib
import json
import os
from collections import Counter
from itertools import combinations

from tradesim import ai
from tradesim.analysis import expected_minutes, team_analysis
from tradesim.checker import _matching, check_trade
from tradesim.picks import label as pick_label
from tradesim.rotation import buckets
from tradesim.skills import SKILLS, player_skills, team_skills

SKILL_NAMES = list(SKILLS)
from tradesim.trade_api import _tradeable_from

SUGGEST_VERSION = "stage6-diverse-3"  # 3: results carry a date-validity record
BUCKET_OF = {"G": 0, "F": 1, "C": 2}
MIN_SKILL_FIT = 55
MIN_UPGRADE = 0.75
MIN_MPG = 18
N_CANDIDATES = 60
N_SIMULATE = 6
MAX_PACKAGES_SCREENED = 120  # per candidate, smallest packages first
PACKAGES_KEPT = 6  # best packages kept per candidate (fallbacks for the diversity rule)
WINS_PER_POINT = 2.6  # quick screen only; the final numbers come from the simulation


def position_skills(rotation, league, em=None):
    """{"G"/"F"/"C": {skill: percentile}} for a rotation, weighted by expected minutes (a "G-F"
    splits his minutes)."""
    em = em or expected_minutes(rotation)
    totals = {g: {sk: [0.0, 0.0] for sk in SKILL_NAMES} for g in BUCKET_OF}
    for pid, minutes in em.items():
        if minutes <= 0:
            continue
        bs = buckets(rotation.players[pid]["position"])
        prof = player_skills(league.players[pid])
        for g, b in BUCKET_OF.items():
            if b in bs:
                for sk, v in prof.items():
                    totals[g][sk][0] += v * minutes / len(bs)
                    totals[g][sk][1] += minutes / len(bs)
    return {g: {sk: round(v / w, 1) if w else 50.0 for sk, (v, w) in d.items()} for g, d in totals.items()}


def league_position_skills(engine, league):
    """League average of position_skills over the 30 teams (cached on the engine)."""
    if not hasattr(engine, "_league_position_skills"):
        per_team = [position_skills(r, league) for r in engine.baseline_rotations.values()]
        engine._league_position_skills = {g: {sk: round(sum(t[g][sk] for t in per_team) / len(per_team), 1)
                                              for sk in SKILL_NAMES} for g in BUCKET_OF}
    return engine._league_position_skills


def team_facts(code, engine, league, cba):
    """What the LLM sees: numbers only, no player names."""
    a = team_analysis(code, engine, league, cba)
    rotation = engine.baseline_rotations[code]
    return {
        "position_skills": position_skills(rotation, league),
        "league_position_skills": league_position_skills(engine, league),
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


class SearchState:
    """Where a search starts: the real league, or the league after trades already chosen
    (rosters, payrolls and picks from tradesim.checker.check_trades_in_sequence, rotations from
    the same player moves). Ideas are found, checked and simulated on top of it."""

    def __init__(self, engine, league, chosen_moves=(), chosen_league=None):
        self.engine, self.league = engine, chosen_league or league
        self.chosen_moves = [{"player": m["id"], "from": m["from"], "to": m["to"]}
                             for m in chosen_moves if m["type"] == "player"]
        self.rotations = engine.run(self.chosen_moves)[1]
        # Players in a chosen trade stay put: no flipping a player just acquired, no getting
        # back one just sent away.
        self.locked = {m["player"] for m in self.chosen_moves}
        self._strength = {}

    def strength(self, code):
        if code not in self._strength:
            self._strength[code] = self.rotations[code].expected_strength()
        return self._strength[code]


def find_candidates(code, needs, state, cba, on_date, min_fit=MIN_SKILL_FIT, positions=None):
    rotation = state.rotations[code]
    em = expected_minutes(rotation)
    rated = state.engine.ratings["players"]
    wanted = {BUCKET_OF[p] for p in (positions or needs["positions"])}
    weakest = {}
    for pid, minutes in em.items():
        if minutes >= 12:
            for b in buckets(rotation.players[pid]["position"]):
                weakest[b] = min(weakest.get(b, 99), rotation.players[pid]["impact"])
    out = []
    for pid, p in state.league.players.items():
        if p["team"] == code or not p["on_roster"] or _restricted(p, cba, on_date) or pid in state.locked:
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
        if fit < min_fit or upgrade < MIN_UPGRADE:
            continue
        out.append({"id": pid, "team": p["team"], "salary": p["salary"], "impact": r["impact"], "upgrade": upgrade,
                    "fit": fit, "score": upgrade * min(r["mpg_when_playing"], 34) / 48 + 0.02 * fit})
    out.sort(key=lambda c: -c["score"])
    return out[:N_CANDIDATES]


def _screen(code, partner, outgoing, incoming_id, state, extra=()):
    """Quick expected-strength change (points) for the team and the partner."""
    ratings = state.engine.ratings
    a, b = copy.deepcopy(state.rotations[code]), copy.deepcopy(state.rotations[partner])
    incoming = [state.league.players[incoming_id]] + list(extra)
    a.change([p["id"] for p in outgoing], incoming, ratings)
    b.change([p["id"] for p in incoming], list(outgoing), ratings)
    return a.expected_strength() - state.strength(code), b.expected_strength() - state.strength(partner)


def _packages(code, cand, state, cba, on_date, max_partner_loss, keep=PACKAGES_KEPT):
    """Outgoing packages for one candidate: salary- and roster-feasible for both teams, then
    ranked by the team's quick gain among those costing the partner at most max_partner_loss
    wins (None = no limit). Returns [(team_gain, partner_gain, combo, extra)], best first; the
    runners-up let the diversity rule swap in a package that doesn't reuse a player."""
    league = state.league
    rotation = state.rotations[code]
    em = expected_minutes(rotation)
    core = set(sorted(rotation.players, key=lambda pid: -_contribution(rotation, pid, em))[:3])
    pool = [p for p in league.roster(code)
            if p["id"] not in core and p["id"] not in state.locked and not _restricted(p, cba, on_date)]
    team, partner = league.teams[code], league.teams[cand["team"]]
    n, m = team["standard_contracts"], partner["standard_contracts"]
    lo, hi = cba["roster"]["min_standard"], cba["roster"]["max_standard"]
    # A team short of players (e.g. 13 contracts) must take back more than it sends: add the
    # partner's cheapest tradeable player as a filler.
    fillers = sorted((p for p in league.roster(cand["team"])
                      if p["id"] != cand["id"] and p["id"] not in state.locked and not _restricted(p, cba, on_date)),
                     key=lambda p: p["salary"])[:1]
    found, screened = [], 0
    for k in (1, 2, 3):
        for extra in ([], fillers):
            n_in = 1 + len(extra)
            if not (lo <= n - k + n_in <= hi and lo <= m - n_in + k <= hi):
                continue
            in_sal = cand["salary"] + sum(p["salary"] for p in extra)
            for combo in combinations(pool, k):
                if screened >= MAX_PACKAGES_SCREENED:
                    break
                out_sal = sum(p["salary"] for p in combo)
                t_after = team["team_salary"] - out_sal + in_sal
                p_after = partner["team_salary"] - in_sal + out_sal
                if not _matching(team["team_salary"], t_after, out_sal, in_sal, cba)[0]:
                    continue
                if not _matching(partner["team_salary"], p_after, in_sal, out_sal, cba)[0]:
                    continue
                screened += 1
                gain, partner_gain = _screen(code, cand["team"], combo, cand["id"], state, extra)
                if max_partner_loss is not None and partner_gain * WINS_PER_POINT < -max_partner_loss:
                    continue
                if gain <= 0:
                    continue
                found.append((gain, partner_gain, combo, tuple(extra)))
    found.sort(key=lambda x: -x[0])
    return found[:keep]


def _sweetener(code, upgrade, league, free=lambda asset_id: True):
    """Latest own pick still free (not used by another idea) as a value sweetener: a 1st for
    +2.0 impact, a 2nd for +1.0."""
    rnd = 1 if upgrade >= 2.0 else (2 if upgrade >= 1.0 else None)
    if rnd is None:
        return None
    own = [p for p in league.picks_held(code) if p["kind"] == "own" and p["round"] == rnd and free(p["id"])]
    return max(own, key=lambda p: p["year"]) if own else None


def _assets(moves):
    """Every player and pick in a trade. Outgoing ones are what the diversity rule is about;
    incoming ones (e.g. the same filler player) would also stop two ideas from combining."""
    return [m["id"] for m in moves if m["type"] in ("player", "pick")]


def _player_card(pid, league, engine):
    p, r = league.players[pid], engine.ratings["players"][pid]
    return {"id": pid, "name": p["name"], "position": p.get("position"), "salary": p["salary"],
            "salary_m": round(p["salary"] / 1e6, 1), "impact": round(r["impact"], 1), "age": r.get("age"),
            "team": p["team"]}


def suggest(code, engine, league, cba, on_date, llm=None, index=None, n=None, max_partner_loss="config",
            chosen=None, needs=None):
    """max_partner_loss: drop trades that cost the partner more than this many wins (quick screen
    first, then the simulated number); None = no limit. Defaults come from config/sim.json.

    chosen: trades already picked ({"moves", "league"}: their moves and the league they leave);
    ideas are then searched, checked and simulated on top of them, and win changes are vs that
    starting point. needs: reuse needs found earlier (skips the LLM call)."""
    sc = engine.cfg.get("suggestions", {})
    n = n or sc.get("count", 4)
    if max_partner_loss == "config":
        max_partner_loss = sc.get("max_partner_loss_wins")
    min_gain = sc.get("min_win_gain", 0.0)
    reuse = sc.get("max_asset_reuse", 1)
    state = SearchState(engine, league, (chosen or {}).get("moves", ()), (chosen or {}).get("league"))
    league = state.league
    index = index or ai.NameIndex(engine.league.players, engine.ratings["players"])
    facts = team_facts(code, engine, engine.league, cba)
    needs = needs or ai.team_needs(facts, index, llm)
    ranked_groups = [p["group"] for p in sorted(facts["positions"], key=lambda p: -p["rank"])]
    next_weakest = [g for g, name in ai.POSITIONS.items() if name in ranked_groups[:2]]
    ladder = [("fits the need", MIN_SKILL_FIT, needs["positions"]),
              ("partial fit", 40, needs["positions"]),
              ("partial fit", 40, sorted(set(needs["positions"]) | set(next_weakest))),
              ("best available upgrade", 0, list(BUCKET_OF))]

    # Shortlist, best quick gain first. Diversity: a player or pick (outgoing, or a partner's
    # filler coming back) may appear in at most `reuse` ideas, so ideas can be combined; a candidate whose best package reuses an
    # asset falls back to its next package, and the sweetener moves to the next free pick.
    used = Counter()
    free = lambda asset_id: reuse is None or used[asset_id] < reuse
    shortlist, per_partner, seen, n_candidates, n_legal = [], Counter(), set(), 0, 0
    checks = []  # every cap check the search makes; the date only matters through these (see cached_suggest)
    for match, min_fit, positions in ladder:
        candidates = [c for c in find_candidates(code, needs, state, cba, on_date, min_fit, positions)
                      if c["id"] not in seen]
        seen.update(c["id"] for c in candidates)
        n_candidates += len(candidates)
        options = sorted(((pkg, cand) for cand in candidates
                          for pkg in _packages(code, cand, state, cba, on_date, max_partner_loss)),
                         key=lambda o: -o[0][0])
        taken = set()
        for (gain, partner_gain, combo, extra), cand in options:
            if len(shortlist) >= N_SIMULATE:
                break
            if cand["id"] in taken or per_partner[cand["team"]] >= 2:
                continue
            if not all(free(p["id"]) for p in (*combo, *extra)) or not free(cand["id"]):
                continue
            moves = [{"type": "player", "id": cand["id"], "from": cand["team"], "to": code}]
            moves += [{"type": "player", "id": p["id"], "from": cand["team"], "to": code} for p in extra]
            moves += [{"type": "player", "id": p["id"], "from": code, "to": cand["team"]} for p in combo]
            sweet = _sweetener(code, cand["upgrade"], league, free)
            for option in ([moves + [{"type": "pick", "id": sweet["id"], "from": code, "to": cand["team"]}]]
                           if sweet else []) + [moves]:
                result = check_trade(league, cba, {"moves": option}, on_date)
                checks.append({"moves": option, "digest": _check_digest(result)})
                if result["works"]:
                    n_legal += 1
                    shortlist.append({"candidate": cand, "moves": option, "check": result, "match": match,
                                      "quick": gain, "partner_quick": partner_gain})
                    used.update(_assets(option))
                    taken.add(cand["id"])
                    per_partner[cand["team"]] += 1
                    break
        if len(shortlist) >= N_SIMULATE:
            break

    for t in shortlist:
        moves = [{"player": m["id"], "from": m["from"], "to": m["to"]} for m in t["moves"] if m["type"] == "player"]
        t["sim"] = engine.scenario(moves, state.chosen_moves)
    if max_partner_loss is not None:
        shortlist = [t for t in shortlist
                     if t["sim"]["teams"][t["candidate"]["team"]]["delta"]["mean_wins"]["change"] >= -max_partner_loss]
    shortlist = [t for t in shortlist if t["sim"]["teams"][code]["delta"]["mean_wins"]["change"] >= min_gain]
    shortlist.sort(key=lambda t: -t["sim"]["teams"][code]["delta"]["mean_wins"]["change"])
    # Greedy by simulated win gain, skipping any idea that would push an asset past the limit
    # (a no-op when the shortlist is already disjoint, i.e. reuse = 1).
    chosen_ideas, final_use = [], Counter()
    for t in shortlist:
        assets = _assets(t["moves"])
        if reuse is not None and any(final_use[a] >= reuse for a in assets):
            continue
        chosen_ideas.append(t)
        final_use.update(assets)
        if len(chosen_ideas) >= n:
            break
    facts_sheets, cards = [], []
    for rank, t in enumerate(chosen_ideas, 1):
        partner = t["candidate"]["team"]
        sim_team, sim_partner = t["sim"]["teams"][code], t["sim"]["teams"][partner]
        d = sim_team["delta"]
        gets = [_player_card(m["id"], league, engine) for m in t["moves"] if m["type"] == "player" and m["to"] == code]
        sends = [_player_card(m["id"], league, engine) for m in t["moves"] if m["type"] == "player" and m["from"] == code]
        picks = [league.picks[m["id"]] for m in t["moves"] if m["type"] == "pick"]
        cand_skills = player_skills(league.players[t["candidate"]["id"]])
        chk = t["check"]["teams"]
        card = {
            "rank": rank, "partner": partner, "match": t["match"], "moves": t["moves"], "gets": gets, "sends": sends,
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
            "team": code, "partner": partner,
            "gets": [{**{k: g[k] for k in ("id", "name", "position", "impact", "salary_m")}, "from": partner, "to": code}
                     for g in gets],
            "sends": [{**{k: s[k] for k in ("id", "name", "position", "impact", "salary_m")}, "from": code, "to": partner}
                      for s in sends],
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
            "on_top_of_chosen": bool(state.chosen_moves),
            "rules": {"max_partner_loss_wins": max_partner_loss, "min_win_gain": min_gain, "max_asset_reuse": reuse},
            "searched": {"candidates": n_candidates, "legal_balanced": n_legal, "simulated": len(shortlist)},
            "validity": {"date": on_date.isoformat(), "restricted": _restricted_digest(league, cba, on_date),
                         "checks": checks}}


# --- caching ---------------------------------------------------------------------------------------
# The search depends on the date in only two ways: which players can't be traded yet
# (_restricted) and the cap checks (signing dates, recent-trade windows, exception expiry).
# A result saved on one date is reused on another when both give the same answers there: the
# same untradeable players and the same result for every check the search made. Then every
# step of the search would repeat exactly, so the ideas are identical. That check takes
# milliseconds; the search takes seconds.

BUNDLED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ideas")


def _check_digest(result):
    body = {k: v for k, v in result.items() if k != "date"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _restricted_digest(league, cba, on_date):
    ids = sorted(pid for pid, p in league.players.items() if _restricted(p, cba, on_date))
    return hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:16]


def still_valid(result, league, cba, on_date):
    """True when a saved result is exactly what the search would return on `on_date`."""
    v = result.get("validity")
    if not v:
        return False
    if v["date"] == on_date.isoformat():
        return True
    if _restricted_digest(league, cba, on_date) != v["restricted"]:
        return False
    return all(_check_digest(check_trade(league, cba, {"moves": c["moves"]}, on_date)) == c["digest"]
               for c in v["checks"])


# --- caching (files) ---------------------------------------------------------------------------------------

def cache_path(code, engine, model_name, chosen=None, folder=None):
    """File stem for one search (team, inputs, rules, trades already chosen). Saved results are
    `<stem>.<date>.json`, one per date they were computed on; any of them may still be valid."""
    from tradesim.engine import CACHE_DIR, fingerprint
    chosen_key = json.dumps(chosen["moves"], sort_keys=True) if chosen else ""
    rules = json.dumps(engine.cfg.get("suggestions", {}), sort_keys=True)  # settings change -> new search
    key = hashlib.sha256(f"{SUGGEST_VERSION}:{model_name}:{fingerprint(engine.n_sims, engine.seed, engine.schedule)}:{chosen_key}:{rules}"
                         .encode()).hexdigest()[:16]
    return os.path.join(folder or CACHE_DIR, f"suggestions_{code}_{key}")


def cached_suggest(code, engine, league, cba, on_date, llm=None, index=None, chosen=None, needs=None):
    """Suggestions are slow (several simulations), so they're cached per team, inputs and
    trades already chosen: first the writable cache, then the ideas shipped with the app
    (data/ideas, written by `python -m tradesim.precompute_ideas`). A saved result from another
    date is used only when still_valid() says the search would give the same ideas."""
    model_name = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b") if llm else "no-llm"
    search_league = (chosen or {}).get("league") or league
    stem = cache_path(code, engine, model_name, chosen)
    saved_files = sorted(glob.glob(stem + ".*.json"), reverse=True) + \
        sorted(glob.glob(cache_path(code, engine, model_name, chosen, BUNDLED_DIR) + ".*.json"), reverse=True)
    for candidate in saved_files:  # newest first
        try:
            with open(candidate) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            continue
        if still_valid(saved, search_league, cba, on_date):
            return {**_public(saved), "from_cache": True}
    result = suggest(code, engine, league, cba, on_date, llm, index, chosen=chosen, needs=needs)
    path = f"{stem}.{on_date.isoformat()}.json"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(result, f)
    except OSError:
        pass  # no writable cache: the result is still returned
    return {**_public(result), "from_cache": False}


def _public(result):
    return {k: v for k, v in result.items() if k != "validity"}
