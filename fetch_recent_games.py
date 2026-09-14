import json
import os

from nba_api.stats.endpoints import leaguegamefinder
from nba_api.stats.static import teams

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_OUTPUT_PATH = os.path.join(_DATA_DIR, "recent_games.json")

_TRACKED_TEAMS = {
    "Spurs": "San Antonio Spurs",
    "Celtics": "Boston Celtics",
    "Nets": "Brooklyn Nets",
    "Kings": "Sacramento Kings",
    "Hawks": "Atlanta Hawks",
    "Hornets": "Charlotte Hornets",
    "Bulls": "Chicago Bulls",
    "Cavaliers": "Cleveland Cavaliers",
    "Mavericks": "Dallas Mavericks",
    "Nuggets": "Denver Nuggets",
    "Pistons": "Detroit Pistons",
    "Warriors": "Golden State Warriors",
    "Rockets": "Houston Rockets",
    "Pacers": "Indiana Pacers",
    "Clippers": "Los Angeles Clippers",
    "Lakers": "Los Angeles Lakers",
    "Grizzlies": "Memphis Grizzlies",
    "Heat": "Miami Heat",
    "Bucks": "Milwaukee Bucks",
    "Timberwolves": "Minnesota Timberwolves",
    "Pelicans": "New Orleans Pelicans",
    "Knicks": "New York Knicks",
    "Thunder": "Oklahoma City Thunder",
    "Magic": "Orlando Magic",
    "76ers": "Philadelphia 76ers",
    "Suns": "Phoenix Suns",
    "TrailBlazers": "Portland Trail Blazers",
    "Raptors": "Toronto Raptors",
    "Jazz": "Utah Jazz",
    "Wizards": "Washington Wizards",
}

_SEASON = "2025-26"


def _team_id_by_short_name():
    lookup = {}
    for short_name, full_name in _TRACKED_TEAMS.items():
        matches = teams.find_teams_by_full_name(full_name)
        if not matches:
            raise ValueError(f"No team found for {full_name}")
        lookup[matches[0]["id"]] = short_name
    return lookup


def _opponent_from_matchup(matchup):
    separator = " vs. " if " vs. " in matchup else " @ "
    return matchup.split(separator)[1]


def fetch_season_games():
    df = leaguegamefinder.LeagueGameFinder(
        season_nullable=_SEASON,
        season_type_nullable="Regular Season",
        league_id_nullable="00",
        timeout=30,
    ).get_data_frames()[0]
    df = df.sort_values("GAME_DATE")

    by_team_id = {}
    for row in df.to_dict("records"):
        team_id = int(row["TEAM_ID"])
        pts_for = row["PTS"]
        pts_against = pts_for - row["PLUS_MINUS"]
        by_team_id.setdefault(team_id, []).append({
            "date": row["GAME_DATE"],
            "opponent": _opponent_from_matchup(row["MATCHUP"]),
            "result": row["WL"],
            "pts_for": int(pts_for),
            "pts_against": int(round(pts_against)),
        })
    return by_team_id


def main():
    team_ids = _team_id_by_short_name()
    games = {
        "_note": f"Live data pulled via nba_api (LeagueGameFinder), {_SEASON} Regular Season only. Re-run fetch_recent_games.py to refresh.",
    }

    print(f"Fetching {_SEASON} league game log...")
    by_team_id = fetch_season_games()
    for team_id, short_name in team_ids.items():
        games[short_name] = by_team_id.get(team_id, [])

    with open(_OUTPUT_PATH, "w") as f:
        json.dump(games, f, indent=2)
    print(f"Wrote {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
