import json
import os
import time

from nba_api.stats.endpoints import leaguedashplayerstats
from nba_api.stats.static import teams

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_OUTPUT_PATH = os.path.join(_DATA_DIR, "player_advanced_stats.json")

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


def _team_id_by_short_name():
    lookup = {}
    for short_name, full_name in _TRACKED_TEAMS.items():
        matches = teams.find_teams_by_full_name(full_name)
        if not matches:
            raise ValueError(f"No team found for {full_name}")
        lookup[matches[0]["id"]] = short_name
    return lookup


def fetch_season_player_advanced_stats(season):
    df = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        measure_type_detailed_defense="Advanced",
        season_type_all_star="Regular Season",
        timeout=30,
    ).get_data_frames()[0]

    by_team_id = {}
    for row in df.to_dict("records"):
        team_id = int(row["TEAM_ID"])
        by_team_id.setdefault(team_id, []).append({
            "player": row["PLAYER_NAME"],
            "gp": int(row["GP"]),
            "min": round(row["MIN"], 1),
            "ts_pct": round(row["TS_PCT"], 3),
            "usg_pct": round(row["USG_PCT"], 3),
            "pie": round(row["PIE"], 3),
            "off_rating": round(row["OFF_RATING"], 1),
            "def_rating": round(row["DEF_RATING"], 1),
        })
    for entries in by_team_id.values():
        entries.sort(key=lambda p: p["pie"], reverse=True)
    return by_team_id


def main():
    team_ids = _team_id_by_short_name()
    stats = {
        "_note": "Live data pulled via nba_api (LeagueDashPlayerStats, Advanced), 2015-16 through 2025-26, Regular Season. PIE (Player Impact Estimate) is the NBA's own single-number impact stat, used here in place of Basketball-Reference's PER, which nba_api does not expose. Re-run fetch_player_advanced_stats.py to refresh.",
    }
    for short_name in _TRACKED_TEAMS:
        stats[short_name] = {}

    for season in _SEASONS:
        print(f"Fetching league player advanced stats for {season}...")
        try:
            by_team_id = fetch_season_player_advanced_stats(season)
            for team_id, short_name in team_ids.items():
                if team_id in by_team_id:
                    stats[short_name][season] = by_team_id[team_id]
        except Exception as e:
            print(f"  FAILED {season}: {e}")
        time.sleep(_REQUEST_DELAY_SECONDS)

    with open(_OUTPUT_PATH, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Wrote {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
