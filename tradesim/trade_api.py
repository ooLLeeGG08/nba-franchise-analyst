"""Trade machine back end (Stage 4): assets per team and trade checks for the UI.

All cap logic stays in tradesim.checker; this module only shapes data for the screen.

Move format (same as the checker): {"type": "player" | "pick" | "cash", "id" (player/pick),
"amount" (cash), "from", "to"}.
"""
from datetime import date

from tradesim.analysis import team_colors
from tradesim.checker import cap_status, check_trade
from tradesim.picks import label as pick_label
from tradesim.teams import TEAM_INFO

MAX_TEAMS = 4


def _thresholds(cba):
    return {"salary_cap": cba["salary_cap"], "tax_line": cba["tax_line"],
            "first_apron": cba["first_apron"], "second_apron": cba["second_apron"]}


def _tradeable_from(player, cba):
    """Earliest date a player signed this league year can be traded (None if no restriction)."""
    acq = player.get("acquired", {})
    if acq.get("type") != "signed" or acq.get("date", "") < cba["league_year_start"]:
        return None
    from tradesim.checker import _add_months, _d
    signed = _d(acq["date"])
    return max(_d(cba["signing_restrictions"]["free_agent_earliest"]),
               _add_months(signed, cba["signing_restrictions"]["free_agent_months"])).isoformat()


def team_assets(code, league, cba):
    """Everything a team can put in a trade, plus its payroll position."""
    team = league.teams[code]
    roster = []
    for p in sorted(league.roster(code), key=lambda p: -p["salary"]):
        roster.append({"id": p["id"], "name": p["name"], "position": p.get("position"), "salary": p["salary"],
                       "no_trade_clause": p.get("no_trade_clause", False), "bird_veto": p.get("bird_veto", False),
                       "tradeable_from": _tradeable_from(p, cba)})
    picks = [{"id": pk["id"], "label": pick_label(pk), "text": pk["text"], "kind": pk["kind"],
              "year": pk["year"], "round": pk["round"], "tradeable": pk["kind"] != "frozen"}
             for pk in sorted(league.picks_held(code), key=lambda p: (p["year"], p["round"], p["id"]))]
    exceptions = [{"id": e["id"], "amount": e["amount"], "expires": e["expires"], "source": e["source_player"],
                   "prior_season": e["prior_season"]} for e in league.exceptions_of(code)]
    return {"code": code, "name": TEAM_INFO[code]["name"], "conference": TEAM_INFO[code]["conference"],
            "colors": team_colors(code), "team_salary": team["team_salary"],
            "status": cap_status(team["team_salary"], cba), "hard_cap": team.get("hard_cap"),
            "standard_contracts": team["standard_contracts"], "thresholds": _thresholds(cba),
            "roster": roster, "picks": picks, "exceptions": exceptions,
            "cash_limit": cba["cash"]["max_per_season"]}


class BadTrade(ValueError):
    pass


def parse_moves(payload, league):
    """Validate the posted moves; raises BadTrade with a short message."""
    if not isinstance(payload, dict) or not isinstance(payload.get("moves"), list):
        raise BadTrade("Send {\"moves\": [...]}.")
    moves = []
    for m in payload["moves"]:
        if not isinstance(m, dict) or m.get("type") not in ("player", "pick", "cash"):
            raise BadTrade("Each move needs a type: player, pick or cash.")
        if m.get("from") not in TEAM_INFO or m.get("to") not in TEAM_INFO:
            raise BadTrade("Each move needs valid from/to teams.")
        if m["type"] == "cash":
            try:
                amount = int(m.get("amount", 0))
            except (TypeError, ValueError):
                raise BadTrade("Cash amount must be a number.")
            moves.append({"type": "cash", "amount": amount, "from": m["from"], "to": m["to"]})
        else:
            if not isinstance(m.get("id"), str):
                raise BadTrade("Player and pick moves need an id.")
            moves.append({"type": m["type"], "id": m["id"], "from": m["from"], "to": m["to"]})
    teams = {m["from"] for m in moves} | {m["to"] for m in moves}
    if len(teams) > MAX_TEAMS:
        raise BadTrade(f"At most {MAX_TEAMS} teams in one trade.")
    return moves


def check(payload, league, cba, on_date=None):
    """Run the cap checker and add what the screen needs (names, colors, thresholds)."""
    moves = parse_moves(payload, league)
    on_date = on_date or date.today()
    if not moves:
        return {"works": False, "empty": True, "errors": ["Add players, picks or cash to build a trade."],
                "teams": {}, "thresholds": _thresholds(cba)}
    result = check_trade(league, cba, {"moves": moves}, on_date)
    for code, t in result["teams"].items():
        t["name"] = TEAM_INFO[code]["name"]
        t["colors"] = team_colors(code)
        t["counts"] = {s: sum(1 for r in t["rules"] if r["status"] == s) for s in ("pass", "fail", "not_checked")}
        if t.get("exception_used"):
            e = league.trade_exceptions[t["exception_used"]["id"]]
            t["exception_used"]["label"] = f"{e['source_player']} trade exception ({e['amount'] / 1e6:.1f}M)"
    result["thresholds"] = _thresholds(cba)
    result["empty"] = False
    return result
