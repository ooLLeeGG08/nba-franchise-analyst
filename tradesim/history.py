"""Basketball-Reference advanced stats for every season, in one shape.

load_season("2021-22") -> (totals, stints)
  totals: {bbref_id: record}  one per player (season totals; traded players' combined row)
  stints: [record with "team" and "bbref_id"] one per player per team

Every file is a Basketball-Reference CSV export with the "Player-additional" column (the
player's BBRef ID), so seasons are joined on that ID, never on names.

Sources and as-of dates for every file are listed in data/raw/SOURCES.json.
"""
import json
import os
from functools import lru_cache

from tradesim.build_data import ROOT, _bbref_rows, parse_bbref, parse_bbref_stints
from tradesim.teams import CODE_BY_NAME

RAW = os.path.join(ROOT, "data", "raw")
CURRENT_SEASON = "2026-27"
BBREF_FILES = {
    "2018-19": "bbref/advanced_2018-19.txt",
    "2019-20": "bbref/advanced_2019-20.txt",
    "2020-21": "bbref/advanced_2020-21.txt",
    "2021-22": "bbref/advanced_2021-22.txt",
    "2022-23": "bbref/advanced_2022-23.txt",
    "2023-24": "bbref/advanced_2023-24.txt",
    "2024-25": "bbref/advanced_2024-25.txt",
    "2025-26": "bbref/advanced_2025-26.txt",
    "2026-27": "bbref/advanced_2026-27_asof_2026-11-09.txt",
}
SEASONS = list(BBREF_FILES)
# nba_api team names that differ from the app's full names.
_TEAM_NAME_ALIASES = {"LA Clippers": "Los Angeles Clippers"}


def previous(season, n=1):
    start = int(season[:4]) - n
    return f"{start}-{str(start + 1)[2:]}"


@lru_cache(maxsize=None)
def _text(season):
    with open(os.path.join(RAW, BBREF_FILES[season]), encoding="utf-8-sig") as f:
        return f.read()


@lru_cache(maxsize=None)
def load_season(season):
    if season not in BBREF_FILES:
        return {}, []
    text = _text(season)
    return parse_bbref(text), parse_bbref_stints(text)


@lru_cache(maxsize=None)
def team_ratings():
    """{season: {team_code: {"games", "net_rating", "possessions"}}} from nba_api."""
    with open(os.path.join(RAW, "team_ratings.json")) as f:
        raw = json.load(f)["seasons"]
    return {season: {CODE_BY_NAME[_TEAM_NAME_ALIASES.get(name, name)]: v for name, v in teams.items()}
            for season, teams in raw.items()}


@lru_cache(maxsize=None)
def draft_history():
    with open(os.path.join(RAW, "draft_history.json")) as f:
        return json.load(f)["picks"]
