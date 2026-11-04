import json
import os
import time

from datetime import datetime, timezone

from nba_api.stats.endpoints import commonteamroster, franchisehistory, teamyearbyyearstats
from nba_api.stats.static import teams

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_OUTPUT_PATH = os.path.join(_DATA_DIR, "team_facts.json")

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

_CURRENT_SEASON = "2025-26"
_REQUEST_DELAY_SECONDS = 0.6


def _team_id(full_name):
    matches = teams.find_teams_by_full_name(full_name)
    if not matches:
        raise ValueError(f"No team found for {full_name}")
    return matches[0]["id"]


def _franchise_title_counts():
    """Live LEAGUE_TITLES per team_id, used only to sanity-check the
    per-season list below against an independent nba_api field -- a
    discrepancy here means the per-season scrape missed something.

    A relocated/renamed franchise (e.g. Minneapolis Lakers -> LA Lakers) gets
    one row per era PLUS one all-time row spanning every era -- the era rows
    are subsets of the all-time row, not additional titles. Keep only the
    row with the longest YEARS span (the all-time total) per team_id."""
    df = franchisehistory.FranchiseHistory(league_id="00", timeout=30).get_data_frames()[0]
    totals = {}
    for row in df.to_dict("records"):
        team_id, years = row["TEAM_ID"], int(row["YEARS"])
        if team_id not in totals or years > totals[team_id][1]:
            totals[team_id] = (int(row["LEAGUE_TITLES"]), years)
    return {team_id: titles for team_id, (titles, _) in totals.items()}


def fetch_championships(team_id):
    df = teamyearbyyearstats.TeamYearByYearStats(team_id=team_id, timeout=30).get_data_frames()[0]
    years = []
    for row in df.to_dict("records"):
        if row.get("NBA_FINALS_APPEARANCE") == "LEAGUE CHAMPION":
            years.append(row["YEAR"])
    return years


def fetch_head_coach(team_id):
    df = commonteamroster.CommonTeamRoster(team_id=team_id, season=_CURRENT_SEASON, timeout=30).get_data_frames()[1]
    head = df[df["COACH_TYPE"] == "Head Coach"]
    if head.empty:
        return None
    return head.iloc[0]["COACH_NAME"]


def main():
    title_counts = _franchise_title_counts()
    now = datetime.now(timezone.utc).isoformat()
    facts = {
        "_note": (
            "Championships and current head coach are pulled live via nba_api -- "
            "TeamYearByYearStats.NBA_FINALS_APPEARANCE for titles (cross-checked against "
            "FranchiseHistory.LEAGUE_TITLES) and CommonTeamRoster's coaches table for the "
            f"current head coach ({_CURRENT_SEASON}). front_office_head is intentionally null: "
            "no live source exists and nothing should be guessed here. Re-run "
            "fetch_team_facts.py to refresh."
        ),
        "generated_at": now,
        "as_of_season": _CURRENT_SEASON,
    }

    mismatches = []
    for short_name, full_name in _TRACKED_TEAMS.items():
        print(f"Fetching facts for {full_name}...")
        team_id = _team_id(full_name)
        try:
            championships = fetch_championships(team_id)
        except Exception as e:
            print(f"  FAILED championships: {e}")
            championships = []
        time.sleep(_REQUEST_DELAY_SECONDS)

        try:
            head_coach = fetch_head_coach(team_id)
        except Exception as e:
            print(f"  FAILED head coach: {e}")
            head_coach = None
        time.sleep(_REQUEST_DELAY_SECONDS)

        franchise_total = title_counts.get(team_id)
        if franchise_total is not None and franchise_total != len(championships):
            mismatches.append((short_name, len(championships), franchise_total))

        facts[short_name] = {
            "championships": championships,
            "championships_source": "nba_api TeamYearByYearStats.NBA_FINALS_APPEARANCE",
            "head_coach": head_coach,
            "head_coach_source": f"nba_api CommonTeamRoster ({_CURRENT_SEASON})",
            "front_office_head": None,
            "front_office_head_source": None,
            "as_of": now,
        }

    with open(_OUTPUT_PATH, "w") as f:
        json.dump(facts, f, indent=2)
    print(f"\nWrote {_OUTPUT_PATH}")
    if mismatches:
        print("\nMISMATCHES vs FranchiseHistory.LEAGUE_TITLES (investigate before trusting):")
        for short_name, per_season_count, franchise_count in mismatches:
            print(f"  {short_name}: per-season count={per_season_count}, FranchiseHistory total={franchise_count}")
    else:
        print("All per-season championship counts match FranchiseHistory.LEAGUE_TITLES.")


if __name__ == "__main__":
    main()
