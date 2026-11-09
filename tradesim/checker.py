"""Trade legality checker: pure code, no LLM, cap rules only (no fairness check).

check_trade() returns, for every team in the trade, a list of rule rows:
    {"group", "id", "label", "status", "detail"}
with status one of:
    pass         the rule was checked and is met
    fail         the rule was checked and is broken (the trade doesn't work)
    not_checked  the data needed to check it is missing; never treated as a pass

All thresholds come from config/cba_2026_27.json via the `cba` dict.

Trade format:
    {"moves": [
        {"type": "player", "id": "tyrese-maxey", "from": "PHI", "to": "ATL"},
        {"type": "pick",   "id": "ATL-2029-R1-0", "from": "ATL", "to": "PHI"},
        {"type": "cash",   "amount": 2000000,     "from": "ATL", "to": "PHI"}]}
"""
from datetime import date, timedelta

from tradesim.picks import label as pick_label, stepien_check

PASS, FAIL, NOT_CHECKED = "pass", "fail", "not_checked"
APRON_NAMES = {"first_apron": "first apron", "second_apron": "second apron"}


def money(x):
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x) / 1e6:,.1f}M"


def _d(value):
    return value if isinstance(value, date) else date.fromisoformat(value)


def _add_months(d, months):
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    days_in_month = [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(d.day, days_in_month))


def cap_status(salary, cba):
    if salary > cba["second_apron"]:
        return "Over the second apron"
    if salary > cba["first_apron"]:
        return "Over the first apron"
    if salary > cba["tax_line"]:
        return "Over the tax"
    if salary > cba["salary_cap"]:
        return "Over the cap"
    return "Under the cap"


def max_incoming(out_salary, cba):
    """Most salary a team below the first apron may take back for `out_salary` (CBA tiers)."""
    for tier in cba["salary_matching"]["tiers"]:
        if tier["max_outgoing"] is None or out_salary <= tier["max_outgoing"]:
            return out_salary * tier["percent"] + tier["plus"]
    raise ValueError("salary_matching.tiers must end with a tier whose max_outgoing is null")


def _matching(before, after, out_sal, in_sal, cba):
    """Salary matching for one team. Returns (ok, detail, method)."""
    sm = cba["salary_matching"]
    if in_sal == 0 and out_sal == 0:
        return True, "No salary changes hands.", "none"
    if after <= cba["salary_cap"]:
        return True, f"Stays under the cap ({money(after)} vs {money(cba['salary_cap'])}).", "cap_room"
    if before < cba["salary_cap"] and after <= cba["salary_cap"] + sm["cap_room_cushion"]:
        return True, f"Fits in cap room plus the {money(sm['cap_room_cushion'])} cushion.", "cap_room"
    if in_sal <= out_sal:
        return True, f"Takes back {money(in_sal)}, no more than the {money(out_sal)} it sends.", "less_back"
    if after >= cba["first_apron"]:
        allowed = out_sal * sm["max_percent_above_first_apron"]
        apron = "second apron" if after > cba["second_apron"] else "first apron"
        if in_sal <= allowed:
            return True, (f"Ends above the {apron}; takes back {money(in_sal)}, within "
                          f"{sm['max_percent_above_first_apron']:.0%} of the {money(out_sal)} it sends."), "apron_100"
        return False, (f"Takes in {money(in_sal - allowed)} more than allowed. Ending at {money(after)}, above the "
                       f"{apron}, a team can take back at most {sm['max_percent_above_first_apron']:.0%} of the "
                       f"{money(out_sal)} it sends."), "apron_100"
    allowed = max_incoming(out_sal, cba)
    if in_sal <= allowed:
        return True, (f"Sends {money(out_sal)}, takes back {money(in_sal)}; up to {money(allowed)} allowed "
                      f"({money(allowed - in_sal)} of room)."), "expanded"
    return False, (f"Takes in {money(in_sal - allowed)} more than salary matching allows: sends {money(out_sal)}, "
                   f"can take back up to {money(allowed)}."), "expanded"


def _row(group, rule_id, label, status, detail):
    return {"group": group, "id": rule_id, "label": label, "status": status, "detail": detail}


def _summarize(rows, ok_detail):
    """Combine per-player sub-results into one rule status."""
    statuses = [s for s, _ in rows]
    if FAIL in statuses:
        return FAIL, " ".join(d for s, d in rows if s == FAIL)
    if NOT_CHECKED in statuses:
        return NOT_CHECKED, " ".join(d for s, d in rows if s == NOT_CHECKED)
    return PASS, ok_detail


# --- structure ----------------------------------------------------------------

def _structure_errors(league, trade):
    errors, seen = [], set()
    moves = trade.get("moves", [])
    teams = {m.get("from") for m in moves} | {m.get("to") for m in moves}
    if len(teams - {None}) < 2:
        errors.append("A trade needs at least two teams.")
    for m in moves:
        frm, to = m.get("from"), m.get("to")
        if frm not in league.teams or to not in league.teams:
            errors.append(f"Unknown team in move {m}.")
            continue
        if frm == to:
            errors.append(f"A team can't trade with itself ({frm}).")
        if m["type"] == "cash":
            if m.get("amount", 0) <= 0:
                errors.append("Cash amount must be positive.")
            continue
        key = (m["type"], m["id"])
        if key in seen:
            errors.append(f"{m['id']} appears twice in this trade.")
        seen.add(key)
        moved_in = getattr(league, "moved_in", {}).get(key)
        if m["type"] == "player":
            p = league.players.get(m["id"])
            if not p:
                errors.append(f"Unknown player {m['id']}.")
            elif p["team"] != frm:
                where = f" (moved there in trade {moved_in + 1})" if moved_in is not None else ""
                errors.append(f"{p['name']} is on {p['team']}{where}, not {frm}.")
            elif not p["on_roster"]:
                errors.append(f"{p['name']} is not on {frm}'s roster (waived).")
        elif m["type"] == "pick":
            pk = league.picks.get(m["id"])
            if not pk or pk["kind"] == "conveyed":
                errors.append(f"Unknown pick {m['id']}.")
            elif pk["holder"] != frm:
                where = f" (moved there in trade {moved_in + 1})" if moved_in is not None else ""
                errors.append(f"{frm} doesn't hold {pick_label(pk)}; {pk['holder']} does{where}.")
        else:
            errors.append(f"Unknown move type {m['type']}.")
    return errors


# --- main check -------------------------------------------------------------------

def check_trade(league, cba, trade, on_date=None):
    on_date = _d(on_date or date.today())
    errors = _structure_errors(league, trade)
    if errors:
        return {"works": False, "errors": errors, "teams": {}, "date": on_date.isoformat()}

    moves = trade["moves"]
    codes = sorted({m["from"] for m in moves} | {m["to"] for m in moves})
    results = {code: _check_team(league, cba, code, moves, on_date) for code in codes}
    return {"works": all(r["works"] for r in results.values()), "errors": [], "teams": results,
            "date": on_date.isoformat()}


def _check_team(league, cba, code, moves, on_date):
    team = league.teams[code]
    out_players = [league.players[m["id"]] for m in moves if m["type"] == "player" and m["from"] == code]
    in_players = [league.players[m["id"]] for m in moves if m["type"] == "player" and m["to"] == code]
    out_picks = [league.picks[m["id"]] for m in moves if m["type"] == "pick" and m["from"] == code]
    in_picks = [league.picks[m["id"]] for m in moves if m["type"] == "pick" and m["to"] == code]
    cash_out = sum(m["amount"] for m in moves if m["type"] == "cash" and m["from"] == code)
    cash_in = sum(m["amount"] for m in moves if m["type"] == "cash" and m["to"] == code)

    out_sal = sum(p["salary"] for p in out_players)
    in_sal = sum(p["salary"] for p in in_players)
    before = team["team_salary"]
    after = before - out_sal + in_sal
    rows = []

    # 1. Salary matching, with a traded player exception if plain matching fails.
    ok, detail, method = _matching(before, after, out_sal, in_sal, cba)
    used_tpe, tpe_rows = None, []
    if not ok:
        used_tpe, tpe_rows = _try_exception(league, cba, code, before, after, out_sal, in_players, on_date)
        if used_tpe:
            ok, detail, method = _matching(before, after, out_sal, in_sal - used_tpe["player"]["salary"], cba)
            detail = (f"{used_tpe['player']['name']} ({money(used_tpe['player']['salary'])}) is absorbed by a trade "
                      f"exception, so he isn't matched. Rest: {detail}")
    rows.append(_row("matching", "salary_matching", "Salary matching", PASS if ok else FAIL, detail))
    in_matched = in_sal - (used_tpe["player"]["salary"] if used_tpe else 0)

    # 2. Aggregation: combining salaries, and players acquired by trade in the last 60 days.
    aggregated = len(out_players) >= 2 and in_matched > max((p["salary"] for p in out_players), default=0)
    days = cba["aggregation"]["recently_acquired_days"]
    if not aggregated:
        rows.append(_row("matching", "aggregation", "Combining salaries", PASS, "No salaries combined."))
    else:
        recent = []
        for p in out_players:
            acq = p["acquired"]
            if acq.get("type") == "traded" and on_date < _d(acq["date"]) + timedelta(days=days):
                recent.append(f"{p['name']} was acquired by trade on {acq['date']}; his salary can't be combined "
                              f"with others until {(_d(acq['date']) + timedelta(days=days)).isoformat()}.")
        rows.append(_row("matching", "aggregation", "Combining salaries", FAIL if recent else PASS,
                         " ".join(recent) or f"Combines {len(out_players)} salaries; none acquired by trade in the "
                                              f"last {days} days."))

    # 3. Trade exceptions.
    if used_tpe:
        e = used_tpe["exception"]
        rows.append(_row("exceptions", "trade_exception", "Trade exception", PASS,
                         f"Used the {e['source_player']} exception ({money(e['amount'])}, expires {e['expires']}) "
                         f"to absorb {used_tpe['player']['name']}."))
    elif ok:
        rows.append(_row("exceptions", "trade_exception", "Trade exception", PASS, "No exception needed."))
    elif tpe_rows:
        rows.append(_row("exceptions", "trade_exception", "Trade exception", FAIL, " ".join(tpe_rows)))
    elif after > cba["second_apron"] and not cba["trade_exception"]["usable_above_second_apron"]:
        rows.append(_row("exceptions", "trade_exception", "Trade exception", FAIL,
                         "Exceptions can't be used above the second apron, so no exception could help."))
    else:
        rows.append(_row("exceptions", "trade_exception", "Trade exception", NOT_CHECKED,
                         f"No exceptions on file for {code}. The data lists only 5 large exceptions, so a smaller "
                         f"one could make this work."))

    # 4. Hard caps (existing ones, plus ones this trade triggers).
    triggers = []
    if team.get("hard_cap"):
        reason = team.get("hard_cap_reason") or "an earlier move"
        triggers.append((team["hard_cap"], f"of an earlier move ({reason[0].lower() + reason[1:]})"))
    if method == "expanded" and in_matched > out_sal:
        triggers.append(("first_apron", "it takes back more salary than it sends"))
    if used_tpe and used_tpe["exception"]["prior_season"]:
        triggers.append(("first_apron", "it uses an exception created last season"))
    if aggregated:
        triggers.append(("second_apron", "it combines salaries"))
    if cash_out:
        triggers.append(("second_apron", "it sends cash"))
    if not triggers:
        rows.append(_row("aprons", "hard_cap", "Hard cap", PASS, "Not hard-capped."))
    else:
        level, reason = min(triggers, key=lambda t: cba[t[0]])
        limit = cba[level]
        reasons = "; ".join(sorted({r for lvl, r in triggers if lvl == level}))
        if after <= limit:
            rows.append(_row("aprons", "hard_cap", "Hard cap", PASS,
                             f"Hard-capped at the {APRON_NAMES[level]} ({money(limit)}) because {reasons}; ends at "
                             f"{money(after)}, {money(limit - after)} below."))
        else:
            rows.append(_row("aprons", "hard_cap", "Hard cap", FAIL,
                             f"Hard-capped at the {APRON_NAMES[level]} ({money(limit)}) because {reasons}; this trade "
                             f"would put them at {money(after)}, {money(after - limit)} over."))
    hard_cap_after = min(triggers, key=lambda t: cba[t[0]])[0] if triggers else None

    # 5. Second-apron limits: no combining salaries, no cash out (exceptions handled in _try_exception).
    if after > cba["second_apron"]:
        bad = []
        if aggregated:
            bad.append("combine salaries")
        if cash_out:
            bad.append("send cash")
        rows.append(_row("aprons", "second_apron", "Second-apron limits", FAIL if bad else PASS,
                         f"Ends above the second apron ({money(after)}), where a team can't {' or '.join(bad)}."
                         if bad else "Ends above the second apron but doesn't combine salaries, send cash or use an "
                                     "exception."))
    else:
        rows.append(_row("aprons", "second_apron", "Second-apron limits", PASS, "Ends below the second apron."))

    # 6. Cash.
    limit = cba["cash"]["max_per_season"]
    if not cash_out and not cash_in:
        rows.append(_row("aprons", "cash", "Cash", PASS, "No cash in this trade."))
    elif max(cash_out, cash_in) > limit:
        rows.append(_row("aprons", "cash", "Cash", FAIL,
                         f"Moves {money(max(cash_out, cash_in))} in cash; the season limit is {money(limit)}."))
    else:
        rows.append(_row("aprons", "cash", "Cash", NOT_CHECKED,
                         f"This trade's cash ({money(max(cash_out, cash_in))}) is within the {money(limit)} season "
                         f"limit, but cash used earlier this season isn't tracked."))

    # 7. Player restrictions.
    rows += _player_rows(league, cba, code, out_players, in_players, on_date)

    # 8. Roster size.
    count = team["standard_contracts"] - len(out_players) + len(in_players)
    lo, hi = cba["roster"]["min_standard"], cba["roster"]["max_standard"]
    started = f" (has {team['standard_contracts']} now)" if not lo <= team["standard_contracts"] <= hi else ""
    rows.append(_row("roster", "roster_size", "Roster size", PASS if lo <= count <= hi else FAIL,
                     f"Ends with {count} standard contracts{started}; must be {lo}-{hi}."))

    # 9. Draft picks.
    rows += _pick_rows(league, cba, code, out_picks, in_picks)

    works = not any(r["status"] == FAIL for r in rows)
    return {
        "team": code,
        "works": works,
        "salary_before": before,
        "salary_after": after,
        "status_before": cap_status(before, cba),
        "status_after": cap_status(after, cba),
        "sends": [{"type": "player", "id": p["id"], "name": p["name"], "salary": p["salary"]} for p in out_players]
                 + [{"type": "pick", "id": p["id"], "label": pick_label(p), "text": p["text"]} for p in out_picks]
                 + ([{"type": "cash", "amount": cash_out}] if cash_out else []),
        "gets": [{"type": "player", "id": p["id"], "name": p["name"], "salary": p["salary"]} for p in in_players]
                + [{"type": "pick", "id": p["id"], "label": pick_label(p), "text": p["text"]} for p in in_picks]
                + ([{"type": "cash", "amount": cash_in}] if cash_in else []),
        "exception_used": ({"id": used_tpe["exception"]["id"], "player": used_tpe["player"]["id"]}
                           if used_tpe else None),
        "hard_cap_after": hard_cap_after,
        "failures": [r["detail"] for r in rows if r["status"] == FAIL],
        "rules": rows,
    }


def _try_exception(league, cba, code, before, after, out_sal, in_players, on_date):
    """Try to absorb one incoming player into one of the team's trade exceptions so the
    rest of the incoming salary matches. Returns (use or None, reasons it couldn't)."""
    rules = cba["trade_exception"]
    reasons = []
    for e in sorted(league.exceptions_of(code), key=lambda e: -e["amount"]):
        name = f"The {e['source_player']} exception ({money(e['amount'])})"
        if on_date > _d(e["expires"]):
            reasons.append(f"{name} expired on {e['expires']}.")
            continue
        if after > cba["second_apron"] and not rules["usable_above_second_apron"]:
            reasons.append(f"{name} can't be used: the team would end above the second apron.")
            continue
        if e["prior_season"] and after >= cba["first_apron"] and not rules["prior_season_usable_above_first_apron"]:
            reasons.append(f"{name} was created last season and can't be used above the first apron.")
            continue
        fits = False
        for p in sorted(in_players, key=lambda p: -p["salary"]):
            if p["salary"] > e["amount"] + rules["padding"]:
                continue
            fits = True
            ok, _, _ = _matching(before, after, out_sal, sum(q["salary"] for q in in_players) - p["salary"], cba)
            if ok:
                return {"exception": e, "player": p}, reasons
        reasons.append(f"{name} is too small to absorb a player and make the rest match." if not fits
                       else f"{name} could absorb one player, but the rest still doesn't match.")
    return None, reasons


def _player_rows(league, cba, code, out_players, in_players, on_date):
    rows = []
    sr = cba["signing_restrictions"]
    season_start = _d(cba["league_year_start"])

    consent = []
    for p in out_players:
        if p.get("no_trade_clause"):
            consent.append((FAIL, f"{p['name']} has a no-trade clause."))
        if p.get("bird_veto"):
            consent.append((FAIL, f"{p['name']} re-signed for one year with Bird rights and can veto trades."))
    status, detail = _summarize(consent, "No outgoing player has a no-trade clause or veto right (per the data file).")
    rows.append(_row("players", "no_trade", "No-trade clauses", status, detail))

    signing = []
    for p in out_players:
        acq = p["acquired"]
        if acq.get("type") == "signed" and _d(acq["date"]) >= season_start:
            signed = _d(acq["date"])
            earliest = max(_d(sr["free_agent_earliest"]), _add_months(signed, sr["free_agent_months"]))
            if on_date < earliest:
                signing.append((FAIL, f"{p['name']} signed on {signed}; he can't be traded until {earliest}."))
            elif on_date < _d(sr["raise_over_20pct_earliest"]):
                signing.append((NOT_CHECKED, f"{p['name']} signed this summer. If he re-signed with a raise over 20%, "
                                             f"he can't be traded until {sr['raise_over_20pct_earliest']}; raise data "
                                             f"isn't available."))
        elif acq.get("type") == "draft" and acq.get("draft_year") == season_start.year:
            signing.append((NOT_CHECKED, f"{p['name']} is a {acq['draft_year']} draft pick. Rookie contracts can be "
                                         f"traded 30 days after signing; his signing date isn't in the data."))
        elif acq.get("type") == "unknown":
            signing.append((NOT_CHECKED, f"How {p['name']} joined {code} isn't in the data."))
    status, detail = _summarize(signing, "No outgoing player is under a recent-signing restriction."
                                if out_players else "No players sent.")
    rows.append(_row("players", "recently_signed", "Recently signed", status, detail))

    if out_players:
        rows.append(_row("players", "extensions", "Extensions and poison pill", NOT_CHECKED,
                         "Not checked: the data has no contract extension dates."))
    else:
        rows.append(_row("players", "extensions", "Extensions and poison pill", PASS, "No players sent."))

    reacquire = []
    for p in in_players:
        acq = p["acquired"]
        traded_by_us = (acq.get("type") == "traded" and acq.get("from_team") == code
                        and _d(acq["date"]) >= season_start)
        if traded_by_us or p["id"] in league.traded_away.get(code, set()):
            reacquire.append((FAIL, f"{code} traded {p['name']} away this season and can't trade for him again "
                                    f"until next season."))
    status, detail = _summarize(reacquire, "No incoming player was traded away by this team this season (based on "
                                           "each player's most recent move)." if in_players else "No players received.")
    rows.append(_row("players", "reacquire", "Re-acquiring a player", status, detail))
    return rows


def _pick_rows(league, cba, code, out_picks, in_picks):
    rows = []
    frozen = [p for p in out_picks if p["kind"] == "frozen"]
    if frozen:
        rows.append(_row("picks", "pick_ownership", "Pick ownership", FAIL,
                         " ".join(f"{pick_label(p)} is frozen (second-apron penalty) and can't be traded."
                                  for p in frozen)))
    else:
        rows.append(_row("picks", "pick_ownership", "Pick ownership", PASS,
                         f"Holds every pick it sends ({len(out_picks)})." if out_picks else "No picks sent."))

    d = cba["draft"]
    years = list(range(d["stepien_first_year"], d["stepien_first_year"] + d["stepien_years"]))
    before = league.first_round_by_year(code)
    out_ids = {p["id"] for p in out_picks}
    after = {}
    for y, ps in before.items():
        kept = [p for p in ps if p["id"] not in out_ids]
        if kept:
            after[y] = kept
    for p in in_picks:
        if p["round"] == 1:
            after.setdefault(p["year"], []).append(p)
    sent_years = sorted({p["year"] for p in out_picks if p["round"] == 1})
    status, detail = stepien_check(code, years, before, after, sent_years)
    rows.append(_row("picks", "stepien", "Stepien Rule", status, detail))

    conditional = [p for p in out_picks + in_picks if p["kind"] == "conditional"]
    if conditional:
        rows.append(_row("picks", "pick_protections", "Protections and swaps", NOT_CHECKED,
                         "Passed on as written; the outcome isn't modelled: "
                         + "; ".join(f"{p['year']} R{p['round']}: \"{p['text']}\"" for p in conditional)))
    else:
        rows.append(_row("picks", "pick_protections", "Protections and swaps", PASS,
                         "No protected or swap picks involved."))
    return rows


# --- applying trades and multi-trade sequences ---------------------------------------

def apply_trade(league, trade, result, on_date):
    """Return a new League with a (working) trade applied."""
    on_date = _d(on_date).isoformat()
    new = league.copy()
    if not hasattr(new, "moved_in"):
        new.moved_in = {}
    index = getattr(league, "_next_index", 0)
    for m in trade["moves"]:
        frm, to = m["from"], m["to"]
        if m["type"] == "player":
            p = new.players[m["id"]]
            p["team"] = to
            p["acquired"] = {"type": "traded", "from_team": frm, "date": on_date}
            new.teams[frm]["team_salary"] -= p["salary"]
            new.teams[frm]["payroll"] -= p["salary"]
            new.teams[to]["team_salary"] += p["salary"]
            new.teams[to]["payroll"] += p["salary"]
            new.teams[frm]["standard_contracts"] -= 1
            new.teams[to]["standard_contracts"] += 1
            new.traded_away.setdefault(frm, set()).add(p["id"])
        elif m["type"] == "pick":
            pk = new.picks[m["id"]]
            if pk["kind"] == "own":
                pk["kind"], pk["original_team"] = "acquired", frm
            pk["holder"] = to
        new.moved_in[(m["type"], m.get("id"))] = index
    for code, r in result["teams"].items():
        new.teams[code]["hard_cap"] = r["hard_cap_after"]
        if r["exception_used"]:
            e = new.trade_exceptions[r["exception_used"]["id"]]
            e["amount"] = max(0, e["amount"] - new.players[r["exception_used"]["player"]]["salary"])
    new._next_index = index + 1
    return new


def check_trades_in_sequence(league, cba, trades, on_date=None):
    """Check trades in order, each against the state left by the earlier working ones.
    A trade that doesn't work isn't applied. Returns (results, final_league)."""
    state = league.copy()
    state.moved_in, state._next_index = {}, 0
    results = []
    for i, trade in enumerate(trades):
        state._next_index = i
        r = check_trade(state, cba, trade, on_date)
        r["index"] = i
        results.append(r)
        if r["works"]:
            state = apply_trade(state, trade, r, on_date or date.today())
    return results, state
