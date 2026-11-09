"""Fetch the game data the simulator needs from nba_api.

- data/raw/2025_26/games.json: every 2025-26 regular-season game with home/away
  team and score. Used to fit the win-probability model and for the backtest.
- data/raw/2026_27/schedule.json: the full 2026-27 regular-season schedule
  (home/away for all 1,230 games). Used for the season simulation.

- data/raw/games/games_<season>.json: every game 2018-19 to 2024-25 (python fetch_games.py
  --history), for fitting the game model on several seasons.

Run:  python fetch_games.py  [--history]
"""
import json
import os
from datetime import date, datetime

from nba_api.stats.endpoints import leaguegamefinder, scheduleleaguev2

ROOT = os.path.dirname(os.path.abspath(__file__))


def fetch_results(season):
    """One row per game: game_id, date, home, away, scores, and a neutral-site flag.

    LeagueGameFinder returns one row per team per game. MATCHUP reads "BOS vs. NYK"
    (BOS at home) or "BOS @ NYK" (BOS away). Neutral-site games (Mexico City, Las
    Vegas, abroad) give both rows the same MATCHUP text, naming a nominal home team.
    """
    df = leaguegamefinder.LeagueGameFinder(season_nullable=season, season_type_nullable="Regular Season",
                                           league_id_nullable="00", timeout=60).get_data_frames()[0]
    rows_by_game = {}
    for row in df.to_dict("records"):
        rows_by_game.setdefault(row["GAME_ID"], []).append(row)
    out = []
    for game_id, rows in rows_by_game.items():
        if len(rows) != 2:
            continue
        matchup = rows[0]["MATCHUP"]
        if " @ " in matchup:
            away, home = matchup.split(" @ ")
        else:
            home, away = matchup.split(" vs. ")
        pts = {r["TEAM_ABBREVIATION"]: int(r["PTS"]) for r in rows}
        out.append({"game_id": game_id, "date": rows[0]["GAME_DATE"], "home": home, "away": away,
                    "home_pts": pts[home], "away_pts": pts[away],
                    "neutral": rows[0]["MATCHUP"] == rows[1]["MATCHUP"]})
    return sorted(out, key=lambda g: (g["date"], g["game_id"]))


def fetch_schedule(season):
    """Regular-season games only (game ids starting with 002), one row per game."""
    df = scheduleleaguev2.ScheduleLeagueV2(season=season, timeout=60).get_data_frames()[0]
    out = []
    for row in df.to_dict("records"):
        if not str(row["gameId"]).startswith("002"):
            continue
        home, away = row["homeTeam_teamTricode"], row["awayTeam_teamTricode"]
        out.append({"game_id": row["gameId"],
                    "date": datetime.strptime(str(row["gameDate"])[:10], "%m/%d/%Y").date().isoformat(),
                    # Tournament knockout games show no teams yet ("TBD").
                    "home": home if isinstance(home, str) else None,
                    "away": away if isinstance(away, str) else None,
                    "status": row.get("gameStatusText")})
    return sorted(out, key=lambda g: (g["date"], g["game_id"]))


def _write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=0)
    print(f"Wrote {path}")


HISTORY_SEASONS = ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"]
# 2019-20 games from July 30, 2020 were played in the Orlando "bubble": no real home court.
BUBBLE_START = "2020-07-30"


def fetch_history():
    """Every regular-season game 2018-19 to 2024-25, for fitting the game model."""
    import time
    today = date.today().isoformat()
    for season in HISTORY_SEASONS:
        games = fetch_results(season)
        for g in games:
            if season == "2019-20" and g["date"] >= BUBBLE_START:
                g["neutral"] = True
        _write(os.path.join(ROOT, "data", "raw", "games", f"games_{season}.json"),
               {"source_url": "https://stats.nba.com/stats/leaguegamefinder (nba_api LeagueGameFinder)",
                "as_of": today, "note": "2019-20 games from 2020-07-30 (Orlando bubble) are marked neutral.",
                "games": games})
        print(f"{season}: {len(games)} games")
        time.sleep(1)


def main():
    today = date.today().isoformat()
    results = fetch_results("2025-26")
    print(f"2025-26: {len(results)} games")
    _write(os.path.join(ROOT, "data", "raw", "2025_26", "games.json"),
           {"_note": f"nba_api LeagueGameFinder 2025-26 regular season, fetched {today}", "games": results})
    schedule = fetch_schedule("2026-27")
    print(f"2026-27 schedule: {len(schedule)} games")
    _write(os.path.join(ROOT, "data", "raw", "2026_27", "schedule.json"),
           {"_note": f"nba_api ScheduleLeagueV2 2026-27 regular season, fetched {today}", "games": schedule})


if __name__ == "__main__":
    import sys
    fetch_history() if "--history" in sys.argv else main()
