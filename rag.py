import json
import os

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

with open(os.path.join(_DATA_DIR, "franchise_knowledge.json")) as f:
    KNOWLEDGE = json.load(f)

with open(os.path.join(_DATA_DIR, "season_records.json")) as f:
    RECORDS = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

with open(os.path.join(_DATA_DIR, "player_leaders.json")) as f:
    LEADERS = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

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
    return [team for team, aliases in _TEAM_ALIASES.items() if any(a in lowered for a in aliases)]


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


def get_team_records(team):
    return RECORDS.get(team)


def get_team_leaders(team):
    return LEADERS.get(team)


def _team_document(team):
    info = KNOWLEDGE[team]
    records = RECORDS.get(team, {})
    return "\n".join([
        f"{info['full_name']} ({team})",
        f"Summary: {info['summary']}",
        f"Championships: {info['championships'] or 'None in this period'}",
        f"Front office continuity: {info['front_office_continuity']}",
        f"Continuity pattern: {info['continuity_pattern']}",
        "Coaches: " + "; ".join(f"{c['name']} ({c['tenure']}) - {c['note']}" for c in info["coaches"]),
        "Key draft history: " + "; ".join(
            f"{d['year']} {d['pick']}: {d['player']} -> {d['outcome']}" for d in info["draft_history"]
        ),
        "Win totals by season: " + ", ".join(f"{season}: {wins}" for season, wins in records.items()),
    ])



def retrieve_context(team):
    if team not in KNOWLEDGE:
        return ""
    return _team_document(team)
