"""NBA ID <-> Basketball-Reference ID.

Players are keyed by NBA ID (nba_api's PLAYER_ID) everywhere; names are display only. Each
player also carries a bbref_id, and Basketball-Reference stats are joined on it.

match_bbref() finds a player's BBRef ID from his name, team and season:
  1. a manual entry in data/raw/id_overrides.json (by NBA ID) wins;
  2. name + team + season: the one BBRef ID with that normalized name on that team in that
     season's Basketball-Reference rows;
  3. name only: accepted only if exactly one BBRef ID has that name in ANY season we have (two
     different players with the same name are reported as ambiguous, never guessed).
Names are compared after name_key() (accents, punctuation, suffixes and known spelling
differences removed), so "Nikola Jokić" (nba_api) = "Nikola Jokic" (Basketball-Reference).
"""
import json
import os
from functools import lru_cache

from tradesim.build_data import ROOT
from tradesim.names import name_key

OVERRIDES_PATH = os.path.join(ROOT, "data", "raw", "id_overrides.json")


@lru_cache(maxsize=None)
def overrides():
    """{nba_id: {"bbref_id": str | None, "name": str, "reason": str}}. bbref_id None = checked by
    hand: no Basketball-Reference row exists yet (e.g. a rookie who hasn't played)."""
    if not os.path.exists(OVERRIDES_PATH):
        return {}
    with open(OVERRIDES_PATH) as f:
        rows = json.load(f)["overrides"]
    out = {}
    for r in rows:
        if not r.get("reason"):
            raise ValueError(f"id_overrides.json: {r.get('name')} needs a reason")
        out[int(r["nba_id"])] = r
    return out


@lru_cache(maxsize=None)
def season_index(season):
    """({(name_key, team): {bbref ids}}, {name_key: {bbref ids}}) for one season."""
    from tradesim.history import load_season
    totals, stints = load_season(season)
    by_team, by_name = {}, {}
    for s in stints:
        by_team.setdefault((name_key(s["name"]), s["team"]), set()).add(s["bbref_id"])
    for bid, rec in totals.items():
        by_name.setdefault(name_key(rec["name"]), set()).add(bid)
    return by_team, by_name


def all_seasons():
    from tradesim.history import SEASONS
    return SEASONS


def match_bbref(name, team, season, nba_id=None):
    """(bbref_id or None, how, candidates). how: "override", "name+team+season", "name only",
    "ambiguous" or "unmatched"."""
    if nba_id is not None and int(nba_id) in overrides():
        return overrides()[int(nba_id)]["bbref_id"], "override", []
    key = name_key(name)
    ids = season_index(season)[0].get((key, team), set()) if season else set()
    if len(ids) == 1:
        return next(iter(ids)), "name+team+season", []
    if len(ids) > 1:
        return None, "ambiguous", sorted(ids)
    every = set().union(*(season_index(s)[1].get(key, set()) for s in all_seasons()))
    if len(every) == 1:
        return next(iter(every)), "name only", []
    return None, ("ambiguous" if every else "unmatched"), sorted(every)
