"""Trade selection and results (Stage 6).

check_sequence: the chosen trades are checked IN ORDER, each against the rosters and payrolls
left by the earlier working ones (tradesim.checker.check_trades_in_sequence). A trade that
reuses a player or pick already moved, or that no longer passes the cap rules after an
earlier trade, is blocked with the reason and left out. Returns each trade's verdict and the
combined payroll effect on every team involved.

simulate_sequence: the working trades' player moves are simulated together against the
baseline (tradesim.engine, same random draws), and explained (tradesim.ai checks).
"""
from tradesim import ai
from tradesim.analysis import team_colors
from tradesim.checker import cap_status, check_trades_in_sequence
from tradesim.teams import TEAM_INFO
from tradesim.trade_api import BadTrade, parse_moves

MAX_TRADES = 12


def parse_trades(payload, league):
    if not isinstance(payload, dict) or payload.get("team") not in TEAM_INFO:
        raise BadTrade("Send {\"team\": \"ATL\", \"trades\": [{\"id\": ..., \"moves\": [...]}]}.")
    trades = payload.get("trades", [])
    if not isinstance(trades, list) or len(trades) > MAX_TRADES:
        raise BadTrade(f"Send a list of at most {MAX_TRADES} trades.")
    out = []
    for i, t in enumerate(trades):
        if not isinstance(t, dict):
            raise BadTrade("Each trade needs moves.")
        out.append({"id": str(t.get("id", i)), "moves": parse_moves({"moves": t.get("moves")}, league)})
    return payload["team"], out


def check_sequence(payload, league, cba, on_date):
    team, trades = parse_trades(payload, league)
    results, final = check_trades_in_sequence(league, cba, [{"moves": t["moves"]} for t in trades], on_date)
    verdicts = []
    for t, r in zip(trades, results):
        reason = None
        if not r["works"]:
            reason = (r["errors"] or [f"{c}: {tm['failures'][0]}" for c, tm in r["teams"].items() if not tm["works"]]
                      or ["Doesn't work."])[0]
        verdicts.append({"id": t["id"], "works": r["works"], "reason": reason,
                         "conflict": bool(r["errors"]) and any("moved there in trade" in e for e in r["errors"])})
    involved = sorted({team} | {m[k] for t, r in zip(trades, results) if r["works"] for m in t["moves"]
                                for k in ("from", "to")})
    payroll = {}
    for code in involved:
        before, after = league.teams[code]["team_salary"], final.teams[code]["team_salary"]
        payroll[code] = {"name": TEAM_INFO[code]["name"], "colors": team_colors(code),
                         "before": before, "after": after, "status_before": cap_status(before, cba),
                         "status_after": cap_status(after, cba),
                         "contracts_after": final.teams[code]["standard_contracts"]}
    return {"team": team, "trades": verdicts, "payroll": payroll,
            "thresholds": {k: cba[k] for k in ("salary_cap", "tax_line", "first_apron", "second_apron")},
            "working": [t for t, v in zip(trades, verdicts) if v["works"]]}


def _results_facts(team, trades, sim, league, ratings):
    t = sim["teams"][team]
    gets, sends = [], []
    for trade in trades:
        for m in trade["moves"]:
            if m["type"] != "player":
                continue
            p = league.players[m["id"]]
            card = {"id": m["id"], "name": p["name"], "position": p.get("position"),
                    "impact": round(ratings["players"][m["id"]]["impact"], 1),
                    "salary_m": round(p["salary"] / 1e6, 1)}
            if m["to"] == team:
                gets.append(card)
            elif m["from"] == team:
                sends.append(card)
    return {"team": team, "gets": gets, "sends": sends, "picks": [],
            "wins_before": round(t["before"]["mean_wins"], 1), "wins_after": round(t["after"]["mean_wins"], 1),
            "win_change": round(t["delta"]["mean_wins"]["change"], 1),
            "playoff_before": round(t["before"]["playoff_pct"] * 100), "playoff_after": round(t["after"]["playoff_pct"] * 100),
            "playoff_change": round(t["delta"]["playoff_pct"]["change"] * 100),
            "range_before": t["before"]["range"], "range_after": t["after"]["range"]}


def simulate_sequence(payload, league, cba, engine, on_date, llm=None, index=None):
    checked = check_sequence(payload, league, cba, on_date)
    team, working = checked["team"], checked["working"]
    moves = [{"player": m["id"], "from": m["from"], "to": m["to"]}
             for t in working for m in t["moves"] if m["type"] == "player"]
    sim = engine.scenario(moves)
    teams = sim["teams"]
    others = []
    for code, t in teams.items():
        if code == team or not t["moved"]:
            continue
        others.append({"code": code, "name": TEAM_INFO[code]["name"], "colors": team_colors(code),
                       "in_trade": t["changed_roster"],
                       "wins_before": t["before"]["mean_wins"], "wins_after": t["after"]["mean_wins"],
                       "win_change": t["delta"]["mean_wins"]["change"], "win_change_mcse": t["delta"]["mean_wins"]["mcse"],
                       "playoff_before": t["before"]["playoff_pct"], "playoff_after": t["after"]["playoff_pct"]})
    others.sort(key=lambda o: (not o["in_trade"], -abs(o["win_change"])))
    me = teams[team]
    facts = _results_facts(team, working, sim, league, engine.ratings)
    index = index or ai.NameIndex(league.players)
    explanation = ai.explain([facts], index, llm)[0] if working else {
        "text": "No trades chosen: this is the season as the rosters stand.", "source": "template"}
    return {
        "team": team, "code": team, "name": TEAM_INFO[team]["name"], "colors": team_colors(team), "n_sims": engine.n_sims,
        "trades": checked["trades"], "applied": len(working), "payroll": checked["payroll"],
        "before": {k: me["before"][k] for k in ("mean_wins", "range", "distribution", "playoff_pct", "play_in_pct",
                                                "top_seed_pct", "mcse")},
        "after": {k: me["after"][k] for k in ("mean_wins", "range", "distribution", "playoff_pct", "play_in_pct",
                                              "top_seed_pct", "mcse")},
        "delta": me["delta"], "others": others, "explanation": explanation,
    }
