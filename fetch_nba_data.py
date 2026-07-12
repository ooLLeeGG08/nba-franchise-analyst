
import json
import os

import pandas as pd
from nba_api.stats.endpoints import teamyearbyyearstats
from nba_api.stats.static import teams

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_OUTPUT_PATH = os.path.join(_DATA_DIR, "season_records.json")

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
    "Clippers": "LA Clippers",
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

_FIRST_SEASON = "2015-16"
_LAST_SEASON = "2025-26"


def _team_id(full_name):
    matches = teams.find_teams_by_full_name(full_name)
    if not matches:
        raise ValueError(f"No team found for {full_name}")
    return matches[0]["id"]


def fetch_team_records(full_name):
    team_id = _team_id(full_name)
    df = teamyearbyyearstats.TeamYearByYearStats(team_id=team_id, timeout=30).get_data_frames()[0]
    df = df[(df["YEAR"] >= _FIRST_SEASON) & (df["YEAR"] <= _LAST_SEASON)]
    return pd.Series(df["WINS"].values, index=df["YEAR"].values).to_dict()


def main():
    records = {
        "_note": "Live data pulled via nba_api (stats.nba.com) for all 30 teams, 2015-16 through 2025-26. Re-run fetch_nba_data.py to refresh.",
    }
    for short_name, full_name in _TRACKED_TEAMS.items():
        print(f"Fetching {full_name}...")
        records[short_name] = fetch_team_records(full_name)

    with open(_OUTPUT_PATH, "w") as f:
        json.dump(records, f, indent=2)
    print(f"Wrote {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
