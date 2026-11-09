"""Build data/2026_27/league.json from the raw source files in data/raw/2026_27/.

Run:  python -m tradesim.build_data

Sources (all in data/raw/2026_27/):
  contracts.txt              every player's 2026-27 salary (434 standard contracts)
  cap_sheet.json             team totals typed from the user's cap screenshot
  roster_status.json         nba_api: position, age, how/when each player was acquired
  bbref_advanced_2025_26.tsv Basketball-Reference 2025-26 advanced stats (BPM etc.)
  draft_picks.txt            future pick ownership 2027-2033
  trade_exceptions.txt       active traded player exceptions
  no_trade_clauses.txt       no-trade clauses and one-year Bird veto rights
  calendar.txt               2026-27 transaction dates
  hard_caps.json             teams hard-capped by offseason moves

The build prints a report of everything it couldn't match, so data problems
show up here instead of as silent wrong answers later.
"""
import csv
import io
import json
import os
import re
from datetime import date, datetime, timedelta

from tradesim.names import name_key, slug
from tradesim.picks import parse_picks_text
from tradesim.teams import CODE_BY_BBREF, CODE_BY_NAME, CODE_BY_SHORT, TEAM_INFO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "2026_27")
OUT = os.path.join(ROOT, "data", "2026_27", "league.json")
CBA_PATH = os.path.join(ROOT, "config", "cba_2026_27.json")


def _read(name):
    return _read_raw("2026_27", name)


def _read_raw(season_dir, name):
    with open(os.path.join(ROOT, "data", "raw", season_dir, name), encoding="utf-8-sig") as f:
        return f.read()


# --- contracts ---------------------------------------------------------------

def parse_contracts(text):
    """The contracts file lists each player as: rank, name, team, $salary, % of cap
    (with a varying number of blank lines between). Anchor on the $ line."""
    tokens = [line.strip() for line in text.splitlines() if line.strip()]
    rows = []
    for i, tok in enumerate(tokens):
        if not tok.startswith("$"):
            continue
        rank, name, team = tokens[i - 3], tokens[i - 2], tokens[i - 1]
        if not rank.isdigit():
            raise ValueError(f"Unexpected contracts layout near {tokens[i - 3:i + 1]}")
        rows.append({"rank": int(rank), "name": name, "team": CODE_BY_NAME[team],
                     "salary": int(tok[1:].replace(",", ""))})
    if [r["rank"] for r in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("Contracts ranks are not 1..N; a record was skipped")
    return rows


# --- Basketball-Reference stats ----------------------------------------------

_STAT_FIELDS = {"G": int, "GS": int, "MP": int, "PER": float, "TS%": float, "USG%": float,
                "OBPM": float, "DBPM": float, "BPM": float, "VORP": float, "WS/48": float,
                # used for skill profiles in trade suggestions (tradesim.skills)
                "3PAr": float, "ORB%": float, "DRB%": float, "TRB%": float, "AST%": float, "STL%": float,
                "BLK%": float, "TOV%": float}


def _tab_rows(text):
    """Tab-separated copy of the table. Rows may be "1. Name" or "2<TAB>Name";
    header rows repeat every 20 lines."""
    lines = text.splitlines()
    header = [h.strip() for h in lines[0].split("\t") if h.strip()]
    for line in lines[1:]:
        cells = [c.strip() for c in line.split("\t")]
        if not any(cells) or cells[0].startswith("League") or cells[0] == "Rk":
            continue
        if cells[0].isdigit():
            cells = cells[1:]
        else:
            cells[0] = re.sub(r"^\d+\.\s*", "", cells[0])
        yield dict(zip(header, cells))


_FIXED_LEAD = re.compile(r"^\s*(\d+)?\s+(.+?)\s+(\d+)\s+(\S+)\s+(\S+)\s")


def _fixed_width_rows(text):
    """Fixed-width copy of the table (columns aligned under a header line). Numbers are
    right-aligned under their column label, and empty cells are blank, so numeric
    columns are cut by the header's label positions. Traded players' per-team rows
    ("CHI stint") sit under their season-total row and take the player's name."""
    lines = text.splitlines()
    hi = next(i for i, line in enumerate(lines) if line.lstrip().startswith("Rk") and "BPM" in line)
    labels = [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", lines[hi])]
    numeric = labels[[lab for lab, _, _ in labels].index("Pos") + 1:]
    parent = None
    for line in lines[hi + 1:]:
        if not line.strip() or line.strip().startswith(("Rk", "-")):
            continue
        m = _FIXED_LEAD.match(line)
        if not m:
            raise ValueError(f"Unexpected line in fixed-width stats: {line[:60]!r}")
        rank, name, age, team, pos = m.groups()
        if rank:
            parent = name
        elif name.endswith(" stint"):
            name = parent
        row = {"Player": name, "Age": age, "Team": team, "Pos": pos}
        prev_end = labels[[lab for lab, _, _ in labels].index("Pos")][2]
        for label, _, end in numeric:
            if label == "Awards":
                break
            row[label] = line[prev_end:end].strip()
            prev_end = end
        yield row


def _csv_rows(text):
    """Basketball-Reference "Get table as CSV" export (first line "Rk,Player,...")."""
    for row in csv.DictReader(io.StringIO(text)):
        if (row.get("Rk") or "").isdigit():
            yield row


def _bbref_rows(text):
    """Yield every player row (season totals and per-team rows) from any of the three formats
    the exports have come in: CSV, tab-separated, or fixed-width columns."""
    first = text.lstrip("\ufeff").splitlines()[0]
    if first.startswith("Rk,Player"):
        raw_rows = _csv_rows(text)
    elif "\t" in first:
        raw_rows = _tab_rows(text)
    else:
        raw_rows = _fixed_width_rows(text)
    for row in raw_rows:
        if row.get("Player") in (None, "", "Player"):
            continue
        rec = {"name": row["Player"], "bbref_team": row["Team"], "pos": row["Pos"],
               "age": int(row["Age"]) if row["Age"].isdigit() else None}
        for field, cast in _STAT_FIELDS.items():
            value = row.get(field, "")
            rec[field.lower().replace("%", "_pct").replace("/", "_per_")] = cast(value) if value != "" else None
        yield rec


def parse_bbref(text):
    """One record per player. Players who changed teams have a combined "2TM"/"3TM"
    row first; keep that one (whole-season numbers)."""
    stats = {}
    for rec in _bbref_rows(text):
        stats.setdefault(name_key(rec["name"]), rec)
    return stats


def parse_bbref_stints(text):
    """One record per player per team (the per-team rows; combined 2TM/3TM rows skipped)."""
    return [{**rec, "team": CODE_BY_BBREF[rec["bbref_team"]]}
            for rec in _bbref_rows(text) if not re.fullmatch(r"\dTM", rec["bbref_team"])]


# --- roster status (how acquired) ----------------------------------------------

def parse_how_acquired(text):
    if not text:
        return {"type": "unknown"}
    m = re.match(r"^Signed on (\d{2}/\d{2}/\d{2})$", text)
    if m:
        return {"type": "signed", "date": _mdy(m.group(1))}
    m = re.match(r"^#(\d+) Pick in (\d{4}) Draft$", text)
    if m:
        return {"type": "draft", "pick": int(m.group(1)), "draft_year": int(m.group(2))}
    m = re.match(r"^(Draft Rights )?Traded from ([A-Z]{3}) on (\d{2}/\d{2}/\d{2})$", text)
    if m:
        return {"type": "draft_rights_traded" if m.group(1) else "traded",
                "from_team": m.group(2), "date": _mdy(m.group(3))}
    m = re.match(r"^Awarded on Waivers on (\d{2}/\d{2}/\d{2})$", text)
    if m:
        return {"type": "waivers", "date": _mdy(m.group(1))}
    return {"type": "unknown", "text": text}


def _mdy(s):
    return datetime.strptime(s, "%m/%d/%y").date().isoformat()


# --- small text files ------------------------------------------------------------

def parse_trade_exceptions(text, league_year_start):
    out = []
    for m in re.finditer(r"\* (.+?): \$([\d,]+) \((.+?) Trade\) \| Expires: (\d{2}/\d{2}/\d{4})", text):
        team = CODE_BY_NAME[m.group(1).strip()]
        expires = datetime.strptime(m.group(4), "%m/%d/%Y").date()
        created = expires.replace(year=expires.year - 1)
        out.append({"id": f"TPE-{team}-{slug(m.group(3))}", "team": team, "amount": int(m.group(2).replace(",", "")),
                    "source_player": m.group(3).strip(), "created": created.isoformat(),
                    "expires": expires.isoformat(), "prior_season": created.isoformat() < league_year_start})
    return out


def parse_no_trade(text):
    ntc, veto = [], []
    section = None
    for line in text.splitlines():
        if "NO-TRADE CLAUSE (NTC)" in line:
            section = "ntc"
        elif "VETO RIGHTS" in line and line.strip().startswith("2."):
            section = "veto"
        elif line.startswith("* ") and section == "ntc":
            m = re.match(r"\* (.+?)(?: \((.+)\))?$", line.strip())
            ntc.append({"name": m.group(1), "team_in_file": m.group(2)})
        elif line.startswith("* ") and section == "veto":
            veto += [{"name": n.strip()} for n in line[2:].split(",")]
    return ntc, veto


def parse_calendar(text):
    out = []
    for m in re.finditer(r"\* (\w+ \d{1,2}, \d{4})(?: \(([^)]*)\))?: (.+)", text):
        out.append({"date": datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat(),
                    "time": m.group(2), "event": m.group(3).strip()})
    return out


# --- build -------------------------------------------------------------------------

def build(write=True):
    with open(CBA_PATH) as f:
        cba = json.load(f)
    report = []

    contracts = parse_contracts(_read("contracts.txt"))
    roster_status = json.loads(_read("roster_status.json"))
    stats = parse_bbref(_read("bbref_advanced_2025_26.tsv"))
    stats_prev = parse_bbref(_read_raw("2024_25", "bbref_advanced_2024_25.txt"))
    cap_sheet = json.loads(_read("cap_sheet.json"))["teams"]
    hard_caps = json.loads(_read("hard_caps.json"))["teams"]

    rostered = {}
    for short, rows in roster_status["teams"].items():
        for r in rows:
            rostered[name_key(r["PLAYER"])] = {**r, "team": CODE_BY_SHORT[short]}

    players, seen = {}, set()
    for c in contracts:
        key = name_key(c["name"])
        if key in seen:
            raise ValueError(f"Duplicate player in contracts: {c['name']}")
        seen.add(key)
        rs = rostered.get(key)
        on_roster = bool(rs) and rs["team"] == c["team"]
        if rs and rs["team"] != c["team"]:
            report.append(f"team mismatch: {c['name']} contract={c['team']} roster={rs['team']}")
        if not rs:
            report.append(f"not on any 2026-27 roster (treated as waived/dead money): {c['name']} ({c['team']})")
        st = stats.get(key)
        st_prev = stats_prev.get(key)
        players[slug(c["name"])] = {
            "id": slug(c["name"]),
            "name": rs["PLAYER"] if rs else c["name"],
            "team": c["team"],
            "salary": c["salary"],
            "on_roster": on_roster,
            "position": rs["POSITION"] if rs else (st["pos"] if st else None),
            "age": rs["AGE"] if rs else None,
            "experience": rs["EXP"] if rs else None,
            "nba_id": rs["PLAYER_ID"] if rs else None,
            "acquired": parse_how_acquired(rs["HOW_ACQUIRED"]) if rs else {"type": "unknown"},
            "stats_2025_26": st,
            "stats_2024_25": st_prev,
            "no_trade_clause": False,
            "bird_veto": False,
        }

    no_stats = [p["name"] for p in players.values() if p["on_roster"] and not p["stats_2025_26"]]
    report.append(f"{len(no_stats)} rostered contract players have no 2025-26 stats (rookies, injured all season): "
                  + ", ".join(no_stats))
    fallback = [p["name"] for p in players.values() if p["on_roster"] and not p["stats_2025_26"] and p["stats_2024_25"]]
    report.append(f"{len(fallback)} of them have 2024-25 stats to fall back on: " + ", ".join(fallback))

    ntc, veto = parse_no_trade(_read("no_trade_clauses.txt"))
    for entry, flag in [(e, "no_trade_clause") for e in ntc] + [(e, "bird_veto") for e in veto]:
        pid = slug(entry["name"])
        if pid not in players:
            report.append(f"{flag}: {entry['name']} not found in contracts")
            continue
        players[pid][flag] = True
        file_team = entry.get("team_in_file")
        if file_team and CODE_BY_NAME.get(file_team) != players[pid]["team"]:
            report.append(f"{flag}: file lists {entry['name']} with {file_team}, but he is on "
                          f"{players[pid]['team']}; applied to his current team")

    teams = {}
    for code, info in TEAM_INFO.items():
        roster = [p for p in players.values() if p["team"] == code]
        payroll = sum(p["salary"] for p in roster)
        sheet = cap_sheet[info["name"]]
        total = round((cba["first_apron"] / 1e6 - sheet["apron1_room"]) * 1e6)
        total2 = round((cba["second_apron"] / 1e6 - sheet["apron2_room"]) * 1e6)
        if abs(total - total2) > 150_000:
            report.append(f"{code}: cap sheet apron columns disagree ({total:,} vs {total2:,})")
        if abs(payroll / 1e6 - sheet["payroll"]) > 0.051:
            report.append(f"{code}: contracts payroll {payroll:,} != cap sheet payroll {sheet['payroll']}M")
        # The sheet is rounded to $0.1M: a gap that small is rounding, not dead money.
        other = total - payroll if abs(total - payroll) > 100_000 else 0
        hc = hard_caps.get(info["name"])
        teams[code] = {
            **info,
            "payroll": payroll,
            "other_cap_charges": other,
            "team_salary": payroll + other,
            "standard_contracts": sum(1 for p in roster if p["on_roster"]),
            "hard_cap": hc["level"] if hc else None,
            "hard_cap_reason": hc["reason"] if hc else None,
        }

    exceptions = parse_trade_exceptions(_read("trade_exceptions.txt"), cba["league_year_start"])
    for e in exceptions:
        src = players.get(slug(e["source_player"]))
        if src and src["acquired"].get("type") == "traded":
            trade_date = date.fromisoformat(src["acquired"]["date"])
            if abs((date.fromisoformat(e["created"]) - trade_date).days) > 1:
                report.append(f"{e['id']}: expiry implies created {e['created']}, but nba_api shows "
                              f"{e['source_player']} traded on {trade_date}")

    picks = parse_picks_text(_read("draft_picks.txt"))
    kinds = {}
    for p in picks:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    report.append(f"picks parsed: {len(picks)} entries {kinds}")

    league = {
        "season": cba["season"],
        "built": date.today().isoformat(),
        "teams": teams,
        "players": players,
        "picks": {p["id"]: p for p in picks},
        "trade_exceptions": {e["id"]: e for e in exceptions},
        "calendar": parse_calendar(_read("calendar.txt")),
        "build_report": report,
    }
    if write:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w") as f:
            json.dump(league, f, indent=1, ensure_ascii=False)
    return league


if __name__ == "__main__":
    result = build()
    print("\n".join(result["build_report"]))
    print(f"\nWrote {OUT}: {len(result['players'])} players, {len(result['picks'])} pick entries, "
          f"{len(result['trade_exceptions'])} trade exceptions")
