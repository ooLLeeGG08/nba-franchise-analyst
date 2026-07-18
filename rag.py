import json
import os
import re

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

with open(os.path.join(_DATA_DIR, "franchise_knowledge.json")) as f:
    KNOWLEDGE = json.load(f)

with open(os.path.join(_DATA_DIR, "season_records.json")) as f:
    RECORDS = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

with open(os.path.join(_DATA_DIR, "player_leaders.json")) as f:
    LEADERS = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

with open(os.path.join(_DATA_DIR, "team_rosters.json")) as f:
    ROSTERS = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

_TEAM_ALIASES = {
    "Spurs": ["spurs", "san antonio"],
    "Celtics": ["celtics", "boston"],
    "Nets": ["nets", "brooklyn", "new jersey"],
    "Kings": ["kings", "sacramento"],
    "Hawks": ["hawks", "atlanta"],
    "Hornets": ["hornets", "charlotte"],
    "Bulls": ["bulls", "chicago"],
    "Cavaliers": ["cavaliers", "cavs", "cleveland"],
    "Mavericks": ["mavericks", "mavs", "dallas"],
    "Nuggets": ["nuggets", "denver"],
    "Pistons": ["pistons", "detroit"],
    "Warriors": ["warriors", "golden state"],
    "Rockets": ["rockets", "houston"],
    "Pacers": ["pacers", "indiana"],
    "Clippers": ["clippers", "la clippers", "los angeles clippers"],
    "Lakers": ["lakers", "los angeles lakers"],
    "Grizzlies": ["grizzlies", "memphis"],
    "Heat": ["heat", "miami"],
    "Bucks": ["bucks", "milwaukee"],
    "Timberwolves": ["timberwolves", "wolves", "minnesota"],
    "Pelicans": ["pelicans", "new orleans"],
    "Knicks": ["knicks", "new york"],
    "Thunder": ["thunder", "oklahoma city", "okc"],
    "Magic": ["magic", "orlando"],
    "76ers": ["76ers", "sixers", "philadelphia"],
    "Suns": ["suns", "phoenix"],
    "TrailBlazers": ["trail blazers", "blazers", "portland"],
    "Raptors": ["raptors", "toronto"],
    "Jazz": ["jazz", "utah"],
    "Wizards": ["wizards", "washington"],
}


def mentioned_teams(query):
    lowered = query.lower()
    return [
        team for team, aliases in _TEAM_ALIASES.items()
        if any(re.search(rf"\b{re.escape(a)}\b", lowered) for a in aliases)
    ]


def resolve_team(message, history):
    teams = mentioned_teams(message)
    if teams:
        return teams[0]
    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        prior_teams = mentioned_teams(turn.get("content", ""))
        if prior_teams:
            return prior_teams[0]
    return None


_SEASON_KEY_RE = re.compile(r"\b(?:19|20)\d{2}-\d{2}\b")
_SEASON_VERBOSE_RE = re.compile(r"\b((?:19|20)\d{2})-((?:19|20)\d{2})\b")
_BARE_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")


def _all_seasons():
    return sorted(next(iter(ROSTERS.values())).keys()) if ROSTERS else []


def _detect_season(text):
    all_seasons = _all_seasons()

    match = _SEASON_KEY_RE.search(text)
    if match and match.group(0) in all_seasons:
        return match.group(0)

    match = _SEASON_VERBOSE_RE.search(text)
    if match:
        candidate = f"{match.group(1)}-{match.group(2)[2:]}"
        if candidate in all_seasons:
            return candidate

    match = _BARE_YEAR_RE.search(text)
    if match:
        year = int(match.group(1))
        candidate = f"{year}-{str(year + 1)[2:]}"
        if candidate in all_seasons:
            return candidate

    return None


def resolve_season(message, history):
    season = _detect_season(message)
    if season:
        return season
    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        season = _detect_season(turn.get("content", ""))
        if season:
            return season
    all_seasons = _all_seasons()
    return all_seasons[-1] if all_seasons else None


def get_team_records(team):
    return RECORDS.get(team)


def get_team_leaders(team):
    return LEADERS.get(team)


def get_team_roster(team, season):
    return ROSTERS.get(team, {}).get(season)


def _team_document(team, season):
    info = KNOWLEDGE[team]
    records = RECORDS.get(team, {})
    lines = [
        f"{info['full_name']} ({team})",
        f"Summary: {info['summary']}",
        f"Championships: {info['championships'] or 'None in this period'}",
        f"Front office continuity: {info['front_office_continuity']}",
        f"Continuity pattern: {info['continuity_pattern']}",
        "Coaches: " + "; ".join(f"{c['name']} ({c['tenure']}) - {c['note']}" for c in info["coaches"]),
        "Key draft history: " + "; ".join(
            f"{d['year']} {d['pick']}: {d['player']} -> {d['outcome']}" for d in info["draft_history"]
        ),
        "Win totals by season: " + ", ".join(f"{s}: {w}" for s, w in records.items()),
    ]

    roster = get_team_roster(team, season)
    if roster:
        lines.append(
            f"Roster ({season}): " + ", ".join(f"{p['player']} ({p['position']})" for p in roster)
        )

    trades = info.get("trade_history", [])
    if trades:
        lines.append(
            "Trade history: " + "; ".join(
                f"{t['season']} {t['trade']} -> {t['outcome']}" for t in trades
            )
        )

    return "\n".join(lines)


def retrieve_context(team, season):
    if team not in KNOWLEDGE:
        return ""
    return _team_document(team, season)
