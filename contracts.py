import json
import os
import unicodedata

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

with open(os.path.join(_DATA_DIR, "contracts.json")) as f:
    _CONTRACTS_RAW = json.load(f)

with open(os.path.join(_DATA_DIR, "league_caps.json")) as f:
    _LEAGUE_CAPS = json.load(f)["seasons"]

# PARTIAL AND UNVERIFIED -- see data/contracts.json's own "_note". Extracted by
# ChatGPT from HoopsHype's public team salary pages on 2026-10-20 and stopped
# before covering every team/player: 28 of 30 teams have at least one real
# salary row (Portland has none), and only ~95 of the league's ~450 players
# are covered at all, mostly each team's top earners. Never treat a lookup
# miss here as "this player has no salary" -- it almost always just means
# this incomplete extract didn't reach them.
CONTRACT_DATA_NOTE = _CONTRACTS_RAW["_note"]


def _strip_accents(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _index_contracts():
    by_player = {}
    for row in _CONTRACTS_RAW["contracts"]:
        if row["salary"] is None:
            continue
        key = _strip_accents(row["player_name"].lower())
        by_player.setdefault(key, []).append(row)
    for rows in by_player.values():
        rows.sort(key=lambda r: r["season"])
    return by_player


_CONTRACTS_BY_PLAYER = _index_contracts()


def get_player_contract(name):
    """This player's known (season, team, salary, option_type) rows, newest
    last, or None if this partial extract never reached them."""
    return _CONTRACTS_BY_PLAYER.get(_strip_accents(name.lower()))


def latest_cap_season():
    seasons = sorted(_LEAGUE_CAPS)
    return seasons[-1] if seasons else None


def get_league_cap_info(season=None):
    season = season if season in _LEAGUE_CAPS else latest_cap_season()
    return _LEAGUE_CAPS.get(season)
