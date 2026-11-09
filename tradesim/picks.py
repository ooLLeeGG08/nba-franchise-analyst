"""Parse the free-text draft-picks file into pick assets, and the Stepien check.

Each line like "First Round: Own; NYK (via POR)" is split into entries. Each
entry gets a `kind`:

- own        "Own": the team's own pick, fully owned
- acquired   "NYK" / "NYK (via POR)": another team's pick, fully owned
- frozen     "Frozen (through 2027-28)": own pick that can't be traded
- conveyed   "To SAN": the team's own pick belongs to someone else (not an asset)
- conditional  anything with protections, swaps or "more favorable of":
               tradeable as written, but its exact outcome isn't modelled

Only own/acquired/frozen/conditional entries are assets the team can trade.
"""
import re

from tradesim.teams import CODE_BY_PICKS, CODE_BY_PICKS_HEADER

_CODE = r"[A-Z]{3}"
_VIA = r"(?: \(via [^()]*(?:\([^()]*\)[^()]*)*\))?"
_OWN = re.compile(r"^Own$")
_ACQUIRED = re.compile(rf"^({_CODE}){_VIA}$")
_CONVEYED = re.compile(rf"^To ({_CODE}){_VIA}$")
_COUNT_PREFIX = re.compile(r"^[\d +]+;\s*")


def _split_top_level(text, sep=";"):
    """Split on `sep` but not inside parentheses or brackets."""
    parts, depth, current = [], 0, []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    parts.append("".join(current).strip())
    return [p for p in parts if p]


def classify(entry):
    """(kind, other_team_code_or_None) for one entry."""
    if _OWN.match(entry):
        return "own", None
    if entry.startswith("Frozen"):
        return "frozen", None
    m = _CONVEYED.match(entry)
    if m and m.group(1) in CODE_BY_PICKS:
        return "conveyed", CODE_BY_PICKS[m.group(1)]
    m = _ACQUIRED.match(entry)
    if m and m.group(1) in CODE_BY_PICKS:
        return "acquired", CODE_BY_PICKS[m.group(1)]
    if re.match(rf"^To {_CODE}\b", entry):
        return "conveyed", CODE_BY_PICKS.get(entry[3:6])
    return "conditional", None


def parse_picks_text(text):
    """Return a list of pick entries (dicts) for every team, year and round."""
    entries, team, year = [], None, None
    for line in text.splitlines():
        m = re.match(r"^--- (.+) ---$", line.strip())
        if m:
            team = CODE_BY_PICKS_HEADER[m.group(1).strip()]
            continue
        m = re.match(r"^Year (\d{4}):$", line.strip())
        if m:
            year = int(m.group(1))
            continue
        m = re.match(r"^\s*(First|Second) Round: (.*)$", line)
        if not m or team is None:
            continue
        rnd = 1 if m.group(1) == "First" else 2
        body = _COUNT_PREFIX.sub("", m.group(2).strip()) if rnd == 2 else m.group(2).strip()
        for n, part in enumerate(_split_top_level(body)):
            if part in ("0", ""):
                continue
            kind, other = classify(part)
            original = team if kind in ("own", "frozen") else (other if kind == "acquired" else None)
            entries.append({
                "id": f"{team}-{year}-R{rnd}-{n}",
                "holder": team,
                "year": year,
                "round": rnd,
                "kind": kind,
                "original_team": original,
                "conveyed_to": other if kind == "conveyed" else None,
                "text": part,
            })
    return entries


def label(pick):
    """Short display label: "2028 1st (NYK)" or "2029 2nd (conditional)"."""
    rnd = "1st" if pick["round"] == 1 else "2nd"
    if pick["kind"] in ("own", "frozen"):
        whose = f"own{' — frozen' if pick['kind'] == 'frozen' else ''}"
    elif pick["kind"] == "acquired":
        whose = pick["original_team"]
    else:
        whose = "conditional"
    return f"{pick['year']} {rnd} ({whose})"


# --- Stepien Rule -----------------------------------------------------------

YES, NO, UNKNOWN = "yes", "no", "unknown"


def first_round_status(held_firsts_for_year):
    """Does a team have a first-round pick in one draft, in the worst case?

    held_firsts_for_year: the first-round assets the team holds (after any
      trades), as pick dicts.

    - yes: holds an unconditional first (own, acquired or frozen), or an
      "Own or ..." swap entry (a swap always leaves the team one pick)
    - no: holds nothing at all
    - unknown: only conditional/protected entries, whose worst case
      can't be worked out from the text
    """
    if any(p["kind"] in ("own", "acquired", "frozen") for p in held_firsts_for_year):
        return YES
    if any(p["kind"] == "conditional" and p["text"].startswith("Own or ") for p in held_firsts_for_year):
        return YES
    if not held_firsts_for_year:
        return NO
    return UNKNOWN


def stepien_check(team, years, held_before, held_after, sent_first_years):
    """Check the Stepien Rule for a team that sends first-round picks.

    held_before/held_after: {year: [first-round pick dicts]} for the team.
    sent_first_years: years of the first-round picks this team sends.
    Returns (status, detail) with status in pass/fail/not_checked.

    Only a NEW violation caused by this trade fails: the data's worst-case
    view can already show gaps for picks with protections that the league
    has approved, so pre-existing gaps are not blamed on this trade.
    """
    if not sent_first_years:
        return "pass", "No first-round picks sent."
    before = {y: first_round_status(held_before.get(y, [])) for y in years}
    after = {y: first_round_status(held_after.get(y, [])) for y in years}
    unknown_pairs = []
    for y in years[:-1]:
        pair = (y, y + 1)
        if not any(s in sent_first_years for s in pair):
            continue
        a, b = after[y], after[y + 1]
        if a == NO and b == NO and not (before[y] == NO and before[y + 1] == NO):
            return "fail", (f"Would leave {team} without a first-round pick in both {y} and {y + 1} "
                            "(Stepien Rule: no gaps in consecutive future drafts).")
        if NO in (a, b) or (a == UNKNOWN and b == UNKNOWN):
            if YES not in (a, b):
                unknown_pairs.append(f"{y}-{y + 1}")
    if unknown_pairs:
        return "not_checked", (f"Depends on protected or conditional picks in {', '.join(unknown_pairs)}; "
                               "their worst case can't be worked out from the pick text.")
    return "pass", f"{team} still has a first-round pick in at least one of every two consecutive drafts."
