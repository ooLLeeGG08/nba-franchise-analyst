"""Fetch what was known on November 9 of past seasons, for the Stage 7 backtest.

For each season 2021-22 to 2025-26, writes data/raw/backtest/asof_nov9_<season>.json:
  players: every player who had played by Nov 9 (inclusive): his team then (last game),
           games and minutes so far.
  teams:   games played and points scored/allowed by Nov 9.
  playoff_teams: the 16 teams that played in that season's playoffs (the actual outcome).

Run:  python fetch_backtest_inputs.py
"""
import json
import os
import time
from datetime import date

from nba_api.stats.endpoints import leaguegamefinder

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "data", "raw", "backtest")
SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
SOURCE = "https://stats.nba.com/stats/leaguegamefinder (nba_api LeagueGameFinder)"


def _finder(**kwargs):
    df = leaguegamefinder.LeagueGameFinder(league_id_nullable="00", timeout=90, **kwargs).get_data_frames()[0]
    time.sleep(1)
    return df


def fetch_season(season):
    cutoff = f"11/09/{season[:4]}"
    players = {}
    df = _finder(player_or_team_abbreviation="P", season_nullable=season, season_type_nullable="Regular Season",
                 date_to_nullable=cutoff)
    for row in sorted(df.to_dict("records"), key=lambda r: r["GAME_DATE"]):
        p = players.setdefault(row["PLAYER_NAME"], {"name": row["PLAYER_NAME"], "games": 0, "minutes": 0.0})
        p["games"] += 1
        p["minutes"] += float(row["MIN"] or 0)
        p["team"] = row["TEAM_ABBREVIATION"]  # team of his latest game by Nov 9
    teams = {}
    df = _finder(player_or_team_abbreviation="T", season_nullable=season, season_type_nullable="Regular Season",
                 date_to_nullable=cutoff)
    for row in df.to_dict("records"):
        t = teams.setdefault(row["TEAM_ABBREVIATION"], {"games": 0, "points_for": 0, "points_against": 0})
        t["games"] += 1
        t["points_for"] += int(row["PTS"])
        t["points_against"] += int(row["PTS"]) - int(row["PLUS_MINUS"])
    playoffs = _finder(player_or_team_abbreviation="T", season_nullable=season, season_type_nullable="Playoffs")
    return {"source_url": SOURCE, "as_of": date.today().isoformat(), "season": season, "cutoff": cutoff,
            "players": sorted(players.values(), key=lambda p: p["name"]), "teams": teams,
            "playoff_teams": sorted(set(playoffs["TEAM_ABBREVIATION"]))}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for season in SEASONS:
        data = fetch_season(season)
        with open(os.path.join(OUT_DIR, f"asof_nov9_{season}.json"), "w") as f:
            json.dump(data, f, indent=1)
        games = [t["games"] for t in data["teams"].values()]
        print(f"{season}: {len(data['players'])} players, teams {len(data['teams'])} "
              f"({min(games)}-{max(games)} games), playoff teams {len(data['playoff_teams'])}")


if __name__ == "__main__":
    main()
