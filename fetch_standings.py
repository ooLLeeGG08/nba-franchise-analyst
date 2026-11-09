"""Fetch official standings (conference, division, final seed) from nba_api.

- data/raw/standings/standings_<season>.json for 2018-19 to 2026-27 (to date): each team's
  conference, division, wins/losses and PlayoffRank (official seed). Past seasons are used
  to check the simulator's tiebreakers against the NBA's own seeding.
- Divisions for 2026-27 come from the 2026-27 file.

Run:  python fetch_standings.py
"""
import json
import os
import time
from datetime import date

from nba_api.stats.endpoints import leaguestandingsv3
from nba_api.stats.static import teams as static_teams

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "data", "raw", "standings")
SEASONS = ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26", "2026-27"]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    abbreviation = {t["id"]: t["abbreviation"] for t in static_teams.get_teams()}
    today = date.today().isoformat()
    for season in SEASONS:
        df = leaguestandingsv3.LeagueStandingsV3(season=season, timeout=60).get_data_frames()[0]
        rows = [{"team": abbreviation[int(r["TeamID"])], "conference": r["Conference"], "division": r["Division"],
                 "wins": int(r["WINS"]), "losses": int(r["LOSSES"]), "playoff_rank": int(r["PlayoffRank"]),
                 "division_rank": int(r["DivisionRank"])} for r in df.to_dict("records")]
        with open(os.path.join(OUT_DIR, f"standings_{season}.json"), "w") as f:
            json.dump({"source_url": "https://stats.nba.com/stats/leaguestandingsv3 (nba_api LeagueStandingsV3)",
                       "as_of": today, "season": season, "teams": rows}, f, indent=1)
        print(season, len(rows))
        time.sleep(1)


if __name__ == "__main__":
    main()
