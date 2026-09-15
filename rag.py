import json
import os
import re
import unicodedata

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

with open(os.path.join(_DATA_DIR, "franchise_knowledge.json")) as f:
    KNOWLEDGE = json.load(f)

with open(os.path.join(_DATA_DIR, "season_records.json")) as f:
    RECORDS = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

with open(os.path.join(_DATA_DIR, "player_leaders.json")) as f:
    LEADERS = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

with open(os.path.join(_DATA_DIR, "team_rosters.json")) as f:
    ROSTERS = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

with open(os.path.join(_DATA_DIR, "team_advanced_stats.json")) as f:
    TEAM_ADVANCED = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

with open(os.path.join(_DATA_DIR, "player_advanced_stats.json")) as f:
    PLAYER_ADVANCED = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

with open(os.path.join(_DATA_DIR, "player_base_stats.json")) as f:
    PLAYER_BASE = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

with open(os.path.join(_DATA_DIR, "recent_games.json")) as f:
    RECENT_GAMES = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

with open(os.path.join(_DATA_DIR, "team_branding.json")) as f:
    BRANDING = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

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


def latest_season():
    seasons = _all_seasons()
    return seasons[-1] if seasons else None


def available_seasons():
    return _all_seasons()


def get_team_knowledge(team):
    return KNOWLEDGE.get(team)


def get_team_advanced_stats(team):
    return TEAM_ADVANCED.get(team)


def get_player_advanced_stats(team, season):
    return PLAYER_ADVANCED.get(team, {}).get(season)


def get_team_recent_games(team, season=None):
    season = season or latest_season()
    return RECENT_GAMES.get(team, {}).get(season)


def get_team_season_snapshot(team, season=None):
    games = get_team_recent_games(team, season)
    if not games:
        return None

    wins = sum(1 for g in games if g["result"] == "W")
    losses = len(games) - wins
    games_played = len(games)

    def total(field):
        return sum(g[field] for g in games)

    fgm, fga = total("fgm"), total("fga")
    fg3m, fg3a = total("fg3m"), total("fg3a")
    ftm, fta = total("ftm"), total("fta")
    pts_for, pts_against = total("pts_for"), total("pts_against")

    return {
        "games_played": games_played,
        "wins": wins,
        "losses": losses,
        "win_pct": round(wins / games_played, 3),
        "ppg": round(pts_for / games_played, 1),
        "opp_ppg": round(pts_against / games_played, 1),
        "point_diff": round((pts_for - pts_against) / games_played, 1),
        "fg_pct": round(fgm / fga, 3) if fga else None,
        "fg3_pct": round(fg3m / fg3a, 3) if fg3a else None,
        "ft_pct": round(ftm / fta, 3) if fta else None,
        "reb": round(total("reb") / games_played, 1),
        "ast": round(total("ast") / games_played, 1),
        "tov": round(total("tov") / games_played, 1),
    }


def get_team_branding(team):
    return BRANDING.get(team)


def get_all_teams():
    return [
        {
            "key": team,
            "full_name": info["full_name"],
            "abbreviation": info["abbreviation"],
            "colors": {"primary": info["primary"], "secondary": info["secondary"]},
        }
        for team, info in BRANDING.items()
    ]


_BASE_STAT_FIELDS = {"ppg": "pts", "apg": "ast", "rpg": "reb", "spg": "stl"}

# Qualifier excludes small-sample noise (e.g. a 1-game callup with an
# efficient garbage-time stretch) that would otherwise dominate an
# unweighted per-game ranking.
_LEADER_MIN_GAMES, _LEADER_MIN_MINUTES_PER_GAME = 20, 15


def get_league_leaders(category, limit=15):
    season = latest_season()

    if category == "pie":
        entries = [
            {"player": p["player"], "team": team, "value": p["pie"]}
            for team, seasons in PLAYER_ADVANCED.items()
            for p in seasons.get(season, [])
            if p["gp"] >= _LEADER_MIN_GAMES and p["min"] >= _LEADER_MIN_MINUTES_PER_GAME
        ]
    elif category in _BASE_STAT_FIELDS:
        field = _BASE_STAT_FIELDS[category]
        entries = [
            {"player": p["player"], "team": team, "value": p[field]}
            for team, seasons in PLAYER_BASE.items()
            for p in seasons.get(season, [])
            if p["gp"] >= _LEADER_MIN_GAMES and p["min"] >= _LEADER_MIN_MINUTES_PER_GAME
        ]
    else:
        return []

    entries.sort(key=lambda e: e["value"], reverse=True)
    return entries[:limit]


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

    advanced = get_team_advanced_stats(team)
    if advanced and season in advanced:
        a = advanced[season]
        lines.append(
            f"Advanced team stats ({season}, live pulled data): "
            f"Off rating {a['off_rating']} (#{a['off_rating_rank']} NBA), "
            f"Def rating {a['def_rating']} (#{a['def_rating_rank']} NBA), "
            f"Net rating {a['net_rating']} (#{a['net_rating_rank']} NBA), "
            f"Pace {a['pace']}, TS% {a['ts_pct'] * 100:.1f}, eFG% {a['efg_pct'] * 100:.1f}"
        )

    player_advanced = get_player_advanced_stats(team, season)
    if player_advanced:
        top_by_pie = sorted(player_advanced, key=lambda p: p["pie"], reverse=True)[:5]
        lines.append(
            f"Player efficiency ({season}, live pulled data, PIE = NBA's own impact stat used in "
            f"place of Basketball-Reference's PER, which isn't available here): " + ", ".join(
                f"{p['player']} (TS% {p['ts_pct'] * 100:.1f}, USG% {p['usg_pct'] * 100:.1f}, "
                f"PIE {p['pie']:.3f}, OFF RTG {p['off_rating']}, DEF RTG {p['def_rating']})"
                for p in top_by_pie
            )
        )

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

    leaders = get_team_leaders(team)
    if leaders:
        category_names = {"ppg": "Points/game", "apg": "Assists/game", "rpg": "Rebounds/game", "spg": "Steals/game"}
        for category, name in category_names.items():
            entries = leaders.get(category)
            if entries:
                lines.append(
                    f"{name} leaders (2015-16 to 2025-26): " + ", ".join(
                        f"{p['player']} ({p['value']})" for p in entries
                    )
                )

    return "\n".join(lines)


def retrieve_context(team, season):
    if team not in KNOWLEDGE:
        return ""
    return _team_document(team, season)


# ---------------------------------------------------------------------------
# Player resolution. There is no standalone player dataset -- only per-team
# rosters/leaders/advanced-stats. This builds a name index from
# player_advanced_stats.json (which carries every rostered player, not just
# top-5 leaders) so a player mentioned by name can be resolved to their team.
# A player traded between tracked teams keeps their full multi-team history;
# "current" team is wherever their most recent season entry places them.

def _strip_accents(text):
    # Users often type player names without diacritics ("Jokic", "Doncic")
    # even though nba_api's canonical names carry them ("Jokić", "Dončić").
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _build_player_index():
    # Keyed by (name_key, team, season) so base stats (PTS/AST/REB/STL/...)
    # can be merged into the matching advanced-stats row below -- both come
    # from the same nba_api endpoint (different measure_type) for the same
    # players/seasons, so every advanced row has a matching base row.
    history_by_key = {}
    for team, seasons in PLAYER_ADVANCED.items():
        for season, players in seasons.items():
            for p in players:
                key = _strip_accents(p["player"].lower())
                history_by_key.setdefault(key, {})[(team, season)] = {"season": season, "team": team, **p}

    for team, seasons in PLAYER_BASE.items():
        for season, players in seasons.items():
            for p in players:
                key = _strip_accents(p["player"].lower())
                entry = history_by_key.get(key, {}).get((team, season))
                if entry:
                    entry.update({k: v for k, v in p.items() if k != "player"})

    canonical = {}
    for key, by_team_season in history_by_key.items():
        entries = sorted(by_team_season.values(), key=lambda e: e["season"])
        canonical[key] = {"name": entries[-1]["player"], "team": entries[-1]["team"], "history": entries}

    token_to_keys = {}
    for key in canonical:
        for token in key.split():
            token_to_keys.setdefault(token, set()).add(key)

    # Only expose a bare first/last name alias when it uniquely identifies one
    # player league-wide (e.g. "lebron" -> LeBron James is safe; "james" is
    # not, since it's also James Harden's first name).
    token_index = {token: canonical[next(iter(keys))] for token, keys in token_to_keys.items() if len(keys) == 1}

    return canonical, token_index


_PLAYER_FULL_NAME_INDEX, _PLAYER_TOKEN_INDEX = _build_player_index()


def mentioned_players(message):
    lowered = _strip_accents(message.lower())
    found = []
    seen_names = set()
    for key in sorted(_PLAYER_FULL_NAME_INDEX, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", lowered):
            name = _PLAYER_FULL_NAME_INDEX[key]["name"]
            if name not in seen_names:
                found.append(name)
                seen_names.add(name)
    for token in sorted(_PLAYER_TOKEN_INDEX, key=len, reverse=True):
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            name = _PLAYER_TOKEN_INDEX[token]["name"]
            if name not in seen_names:
                found.append(name)
                seen_names.add(name)
    return found


def resolve_player(message, history=None):
    found = mentioned_players(message)
    if found:
        return found[0]

    for turn in reversed(history or []):
        if turn.get("role") != "user":
            continue
        result = resolve_player(turn.get("content", ""))
        if result:
            return result
    return None


def get_player_view(name):
    entry = _PLAYER_FULL_NAME_INDEX.get(_strip_accents(name.lower()))
    if not entry:
        return None

    canonical_name, team, player_history = entry["name"], entry["team"], entry["history"]

    position = None
    for season in sorted(ROSTERS.get(team, {}).keys(), reverse=True):
        match = next((p for p in ROSTERS[team][season] if p["player"] == canonical_name), None)
        if match:
            position = match["position"]
            break

    latest = player_history[-1]
    # Real per-game averages for the player's most recent tracked season --
    # not whether they happen to be a top-5 all-time leader for their team
    # (that seed dataset also has an unrelated name/diacritics mismatch with
    # nba_api's canonical names, e.g. "Nikola Jokic" vs "Nikola Jokić").
    season_stats = {
        "ppg": latest.get("pts"),
        "apg": latest.get("ast"),
        "rpg": latest.get("reb"),
        "spg": latest.get("stl"),
    }
    season_stats = {k: v for k, v in season_stats.items() if v is not None}

    return {
        "name": canonical_name,
        "team": team,
        "position": position,
        "branding": get_team_branding(team),
        "history": player_history,
        "seasonStats": season_stats,
    }


_LEADER_STAT_LABELS = (("ppg", "PPG"), ("apg", "APG"), ("rpg", "RPG"), ("spg", "SPG"))


def _player_document(name):
    view = get_player_view(name)
    if not view:
        return ""
    latest = view["history"][-1]
    stat_bits = [f"{label} {view['seasonStats'][cat]}" for cat, label in _LEADER_STAT_LABELS if cat in view["seasonStats"]]
    stat_bits += [
        f"TS% {latest['ts_pct'] * 100:.1f}",
        f"USG% {latest['usg_pct'] * 100:.1f}",
        f"PIE {latest['pie']:.3f}",
        f"OFF RTG {latest['off_rating']}",
        f"DEF RTG {latest['def_rating']}",
    ]
    return (
        f"{view['name']} ({view['team']}, {view['position'] or 'position unknown'}) -- "
        f"{latest['season']} stats: " + ", ".join(stat_bits)
    )


def _player_comparison_document(name_a, name_b):
    docs = [d for d in (_player_document(name_a), _player_document(name_b)) if d]
    if not docs:
        return ""
    return "Player comparison:\n" + "\n".join(docs)


def _league_efficiency_document():
    leaders = get_league_leaders("pie")
    if not leaders:
        return ""
    season = latest_season()
    ranked = ", ".join(f"{i + 1}. {e['player']} ({e['team']}) {e['value']}" for i, e in enumerate(leaders))
    return f"League-wide PIE (efficiency) leaders, {season}, qualified players only (min. 20 GP, 15 MPG): {ranked}"


def build_context(message, history):
    team = resolve_team(message, history)
    season = resolve_season(message, history)
    parts = []

    team_doc = retrieve_context(team, season) if team else ""
    if team_doc:
        parts.append(team_doc)

    current_players = mentioned_players(message)
    if len(current_players) >= 2:
        parts.append(_player_comparison_document(current_players[0], current_players[1]))
    else:
        single_player = current_players[0] if current_players else resolve_player(message, history)
        if single_player:
            parts.append(_player_document(single_player))

    parts.append(_league_efficiency_document())

    return "\n\n".join(p for p in parts if p)
