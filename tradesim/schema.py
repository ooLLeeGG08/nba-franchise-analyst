"""Schema check for data/2026_27/league.json (run by tradesim.build_data before writing).

Every field the app relies on is checked for type and range, plus a few cross-checks
(players keyed by NBA ID, BBRef IDs unique, teams are real codes, standard contracts match the
roster). Returns a
list of problems; an empty list means the file is usable.
"""
import re
from datetime import date

from tradesim.teams import TEAM_INFO

CODES = set(TEAM_INFO)
POSITION = re.compile(r"^(?:[GFC](?:-[GFC])?|PG|SG|SF|PF)$")
PICK_KINDS = {"own", "acquired", "frozen", "conditional", "conveyed"}
ACQUIRED = {"draft", "draft_rights_traded", "signed", "traded", "waivers", "unknown"}
BBREF_ID = re.compile(r"^[a-z][a-z'.-]*\d{2}$")  # e.g. "whitede01"
BBREF_MATCH = {"override", "name+team+season", "name only", "ambiguous", "unmatched"}


def _is_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def _num(value, lo=None, hi=None, kinds=(int, float)):
    return (isinstance(value, kinds) and not isinstance(value, bool)
            and (lo is None or value >= lo) and (hi is None or value <= hi))


def validate_league(league):
    problems = []

    def need(ok, message):
        if not ok:
            problems.append(message)

    for key, kind in (("season", str), ("built", str), ("as_of", str), ("teams", dict), ("players", dict),
                      ("picks", dict), ("trade_exceptions", dict), ("calendar", list), ("build_report", list),
                      ("sources_as_of", dict)):
        need(isinstance(league.get(key), kind), f"top level: '{key}' missing or not a {kind.__name__}")
    if problems:
        return problems
    need(_is_date(league["built"]) and _is_date(league["as_of"]), "top level: 'built' / 'as_of' aren't dates")
    need(all(_is_date(v) for v in league["sources_as_of"].values()), "sources_as_of: every value must be a date")

    teams, players = league["teams"], league["players"]
    need(set(teams) == CODES, f"teams: expected the 30 team codes, got {len(teams)}")
    for code, t in teams.items():
        need(t.get("code") == code, f"team {code}: 'code' doesn't match its key")
        need(_num(t.get("team_salary"), 1, kinds=int), f"team {code}: team_salary must be a positive integer")
        need(_num(t.get("payroll"), 0, kinds=int), f"team {code}: payroll must be a non-negative integer")
        need(_num(t.get("standard_contracts"), 0, 20, kinds=int), f"team {code}: standard_contracts out of range")
        need(t.get("hard_cap") in (None, "first_apron", "second_apron"), f"team {code}: unknown hard_cap value")

    bbref_ids = {}
    for pid, p in players.items():
        where = f"player {pid}"
        need(p.get("id") == pid, f"{where}: 'id' doesn't match its key")
        need(pid == str(p.get("nba_id")), f"{where}: key must be the NBA ID")
        need(p.get("bbref_id") is None or bool(BBREF_ID.match(p["bbref_id"])), f"{where}: bad bbref_id {p.get('bbref_id')!r}")
        need(p.get("bbref_match") in BBREF_MATCH, f"{where}: bbref_match missing or unknown")
        need(isinstance(p.get("name"), str) and p["name"].strip(), f"{where}: name missing")
        need(p.get("team") in CODES, f"{where}: team {p.get('team')!r} isn't a team code")
        need(_num(p.get("salary"), 0, kinds=int), f"{where}: salary must be a non-negative integer")
        need(isinstance(p.get("on_roster"), bool), f"{where}: on_roster must be true/false")
        need(p.get("position") is None or bool(POSITION.match(p["position"])), f"{where}: bad position {p.get('position')!r}")
        need(p.get("age") is None or _num(p["age"], 17, 45), f"{where}: age out of range")
        need(_num(p.get("nba_id"), 1, kinds=int), f"{where}: nba_id must be a positive integer")
        need(isinstance(p.get("acquired"), dict) and p["acquired"].get("type") in ACQUIRED,
             f"{where}: acquired.type missing or unknown")
        need(isinstance(p.get("no_trade_clause"), bool) and isinstance(p.get("bird_veto"), bool),
             f"{where}: no_trade_clause / bird_veto must be true/false")
        for key in ("stats_2025_26", "stats_2024_25"):
            st = p.get(key)
            need(st is None or (isinstance(st, dict) and _num(st.get("mp"), 0)), f"{where}: {key} has no minutes")
        if p.get("bbref_id"):
            need(p["bbref_id"] not in bbref_ids, f"{where}: bbref_id {p['bbref_id']} also used by {bbref_ids.get(p['bbref_id'])}")
            bbref_ids[p["bbref_id"]] = pid

    for code, t in teams.items():
        n = sum(1 for p in players.values() if p.get("team") == code and p.get("on_roster"))
        need(t.get("standard_contracts") == n, f"team {code}: standard_contracts {t.get('standard_contracts')} "
                                                f"but {n} rostered players")

    for kid, k in league["picks"].items():
        where = f"pick {kid}"
        need(k.get("id") == kid, f"{where}: 'id' doesn't match its key")
        need(k.get("holder") in CODES, f"{where}: holder isn't a team code")
        need(_num(k.get("year"), 2026, 2040, kinds=int), f"{where}: year out of range")
        need(k.get("round") in (1, 2), f"{where}: round must be 1 or 2")
        need(k.get("kind") in PICK_KINDS, f"{where}: unknown kind {k.get('kind')!r}")
        need(isinstance(k.get("text"), str), f"{where}: text missing")

    for eid, e in league["trade_exceptions"].items():
        where = f"trade exception {eid}"
        need(e.get("team") in CODES, f"{where}: team isn't a team code")
        need(_num(e.get("amount"), 1, kinds=int), f"{where}: amount must be a positive integer")
        need(_is_date(e.get("created")) and _is_date(e.get("expires")), f"{where}: created / expires aren't dates")

    for i, c in enumerate(league["calendar"]):
        need(_is_date(c.get("date")) and isinstance(c.get("event"), str), f"calendar[{i}]: needs a date and an event")
    return problems
