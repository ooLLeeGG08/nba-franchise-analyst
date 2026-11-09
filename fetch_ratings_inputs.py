"""Fetch (and cache) the nba_api data the player-rating model needs.

- data/raw/draft_history.json: every draft pick 2014-2026 (season, pick, player)
  for the rookie prior by draft slot.
- data/raw/team_ratings.json: each team's net rating, games and possessions per
  season, 2018-19 to 2026-27 (to date), for the team residual.

Each file records its source_url and as_of. Re-run to refresh.
Run:  python fetch_ratings_inputs.py
"""
import json
import os
import time
from datetime import date

from nba_api.stats.endpoints import drafthistory, leaguedashteamstats

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "data", "raw")
SEASONS = ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26", "2026-27"]


def fetch_draft_history(first_year=2014):
    df = drafthistory.DraftHistory(league_id="00", timeout=60).get_data_frames()[0]
    df = df[df["SEASON"].astype(int) >= first_year]
    return [{"draft_year": int(r["SEASON"]), "pick": int(r["OVERALL_PICK"]), "round": int(r["ROUND_NUMBER"]),
             "player": r["PLAYER_NAME"], "team": r["TEAM_ABBREVIATION"]} for r in df.to_dict("records")]


def fetch_team_ratings():
    out = {}
    for season in SEASONS:
        df = leaguedashteamstats.LeagueDashTeamStats(season=season, measure_type_detailed_defense="Advanced",
                                                     timeout=60).get_data_frames()[0]
        out[season] = {r["TEAM_NAME"]: {"games": int(r["GP"]), "net_rating": float(r["NET_RATING"]),
                                        "possessions": float(r["POSS"])} for r in df.to_dict("records")}
        time.sleep(0.6)
    return out


def main():
    today = date.today().isoformat()
    draft = fetch_draft_history()
    with open(os.path.join(RAW, "draft_history.json"), "w") as f:
        json.dump({"source_url": "https://stats.nba.com/stats/drafthistory (nba_api DraftHistory)",
                   "as_of": today, "picks": draft}, f, indent=0)
    print(f"draft history: {len(draft)} picks")
    ratings = fetch_team_ratings()
    with open(os.path.join(RAW, "team_ratings.json"), "w") as f:
        json.dump({"source_url": "https://stats.nba.com/stats/leaguedashteamstats (nba_api, MeasureType=Advanced)",
                   "as_of": today, "seasons": ratings}, f, indent=1)
    print("team ratings:", {s: len(v) for s, v in ratings.items()})


if __name__ == "__main__":
    main()
