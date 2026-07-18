import json
import os
import time

from nba_api.stats.endpoints import commonteamroster
from nba_api.stats.static import teams

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_OUTPUT_PATH = os.path.join(_DATA_DIR, "team_rosters.json")

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

_SEASONS = [
    "2015-16", "2016-17", "2017-18", "2018-19", "2019-20",
    "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26",
]

_REQUEST_DELAY_SECONDS = 0.6


def _team_id(full_name):
    matches = teams.find_teams_by_full_name(full_name)
    if not matches:
        raise ValueError(f"No team found for {full_name}")
    return matches[0]["id"]


def fetch_team_season_roster(team_id, season):
    df = commonteamroster.CommonTeamRoster(team_id=team_id, season=season, timeout=30).get_data_frames()[0]
    return [
        {"player": row["PLAYER"], "position": row["POSITION"]}
        for row in df[["PLAYER", "POSITION"]].to_dict("records")
    ]


def main():
    rosters = {
        "_note": "Live data pulled via nba_api (CommonTeamRoster), 2015-16 through 2025-26. Re-run fetch_team_rosters.py to refresh.",
    }
    for short_name, full_name in _TRACKED_TEAMS.items():
        team_id = _team_id(full_name)
        rosters[short_name] = {}
        for season in _SEASONS:
            print(f"Fetching {full_name} {season}...")
            try:
                rosters[short_name][season] = fetch_team_season_roster(team_id, season)
            except Exception as e:
                print(f"  FAILED {full_name} {season}: {e}")
            time.sleep(_REQUEST_DELAY_SECONDS)

    with open(_OUTPUT_PATH, "w") as f:
        json.dump(rosters, f, indent=2)
    print(f"Wrote {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
