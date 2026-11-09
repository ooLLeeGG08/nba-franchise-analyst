"""Fetch 2026-27 roster status (position, age, experience, how each player was
acquired) from nba_api into data/raw/2026_27/roster_status.json.

"How acquired" gives the signing/trade dates the cap checker needs for the
recently-signed, re-acquire and aggregation rules, e.g. "Signed on 07/06/26"
or "Traded from CHA on 07/10/26".
"""
import json
import os
import time
from datetime import date

from nba_api.stats.endpoints import commonteamroster

from fetch_team_rosters import _TRACKED_TEAMS, _team_id

SEASON = "2026-27"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "raw", "2026_27", "roster_status.json")
COLUMNS = ["PLAYER", "POSITION", "AGE", "EXP", "HOW_ACQUIRED", "PLAYER_ID"]


def main():
    out = {"_note": f"nba_api CommonTeamRoster {SEASON}, fetched {date.today().isoformat()}", "teams": {}}
    for short_name, full_name in _TRACKED_TEAMS.items():
        df = commonteamroster.CommonTeamRoster(team_id=_team_id(full_name), season=SEASON, timeout=30).get_data_frames()[0]
        rows = df[COLUMNS].to_dict("records")
        for row in rows:
            row["HOW_ACQUIRED"] = row["HOW_ACQUIRED"] if isinstance(row["HOW_ACQUIRED"], str) else None
            row["PLAYER_ID"] = int(row["PLAYER_ID"])
            row["AGE"] = float(row["AGE"]) if row["AGE"] == row["AGE"] else None
        out["teams"][short_name] = rows
        print(f"{short_name}: {len(rows)} players")
        time.sleep(0.6)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
