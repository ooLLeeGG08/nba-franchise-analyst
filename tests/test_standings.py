"""Standings, tiebreakers and play-in tests (sim-accuracy Stage 5)."""
import numpy as np
import pytest

from tradesim.engine import Engine
from tradesim.games import load_schedule_2026_27
from tradesim.league import League
from tradesim.model import load_sim_config
from tradesim.standings import CODES, INDEX, SeasonTable, check_against_official, divisions, play_in
from tradesim.teams import TEAM_INFO

EAST = [c for c in CODES if TEAM_INFO[c]["conference"] == "East"]
WEST = [c for c in CODES if TEAM_INFO[c]["conference"] == "West"]


def league_table(bonus, overrides=(), seed=0):
    """Every pair plays twice and splits 1-1. Team t then beats bonus[t] West (or East) teams
    twice instead of splitting, which separates records. overrides: (winner, loser) pairs that
    become 2-0 instead of 1-1 (winner +1, loser -1)."""
    n = len(CODES)
    G = np.full((n, n), 2.0) - 2 * np.eye(n)
    W = np.full((n, n), 1.0) - np.eye(n)
    for team, b in bonus.items():
        others = WEST if team in EAST else EAST
        for opp in others[:b]:
            W[INDEX[team], INDEX[opp]] += 1
            W[INDEX[opp], INDEX[team]] -= 1
    for winner, loser in overrides:
        W[INDEX[winner], INDEX[loser]] += 1
        W[INDEX[loser], INDEX[winner]] -= 1
    return SeasonTable(W, G, np.zeros(n), divisions(), np.random.default_rng(seed))


def distinct_bonus(tied, tied_value):
    """Distinct records for every East team except `tied`, which all get tied_value."""
    out, value = {}, 15
    for team in EAST:
        if team in tied:
            out[team] = tied_value
        else:
            value -= 1 if value - 1 != tied_value else 2
            out[team] = max(value, 0)
    return out


def test_two_team_tie_broken_by_head_to_head():
    # ATL sweeps BOS (2-0); to keep records level, BOS gets one extra win and ATL one extra loss.
    t = league_table(distinct_bonus({"ATL", "BOS"}, 8), [("ATL", "BOS"), ("BOS", "GSW"), ("DEN", "ATL")])
    assert t.pct["ATL"] == t.pct["BOS"]
    order = t.seeds("East")
    assert order.index("ATL") < order.index("BOS")


def test_two_team_tie_with_split_series_goes_to_division_winner():
    # BOS and ATL tied, 1-1 head to head. BOS has the best record in the Atlantic; ATL is
    # behind MIA and ORL in the Southeast. So BOS wins the tie as a division winner.
    bonus = distinct_bonus({"ATL", "BOS"}, 8)
    bonus.update({"MIA": 14, "ORL": 13, "BKN": 1, "NYK": 2, "PHI": 3, "TOR": 4})
    t = league_table(bonus)
    assert "BOS" in t.division_winners() and "ATL" not in t.division_winners()
    order = t.seeds("East")
    assert order.index("BOS") < order.index("ATL")


def test_three_team_tie_restarts_after_division_winner():
    # BOS (Atlantic winner), ATL and CHI tied. Step 1 puts BOS first; ATL vs CHI restarts as a
    # two-team tie and goes to head-to-head (CHI swept ATL; records rebalanced).
    bonus = distinct_bonus({"ATL", "BOS", "CHI"}, 8)
    bonus.update({"MIA": 14, "ORL": 13, "CLE": 12, "DET": 11, "BKN": 1, "NYK": 2, "PHI": 3, "TOR": 4})
    t = league_table(bonus, [("CHI", "ATL"), ("ATL", "GSW"), ("DEN", "CHI")])
    assert t.pct["ATL"] == t.pct["BOS"] == t.pct["CHI"]
    order = t.seeds("East")
    assert order.index("BOS") < order.index("CHI") < order.index("ATL")


def test_unbreakable_tie_is_random_but_reproducible():
    a = league_table({c: 0 for c in EAST}, seed=3).seeds("East")
    b = league_table({c: 0 for c in EAST}, seed=3).seeds("East")
    assert a == b and sorted(a) == sorted(EAST)


def test_tiebreakers_match_official_nba_seeds():
    """Real results 2018-19 and 2021-22 to 2025-26: every seed matches the NBA's
    (25 two-team and 5 three-team ties across these seasons)."""
    for season in ("2018-19", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"):
        assert check_against_official(season) == [], season


def test_known_official_quirks():
    # 2019-20: non-bubble teams' standings were frozen in March (WAS stayed 9th).
    assert {m["team"] for m in check_against_official("2019-20")} == {"CHA", "WAS"}
    # 2020-21: the official ranks include the play-in result (MEM won the 8th spot).
    assert {m["team"] for m in check_against_official("2020-21")} == {"GSW", "MEM"}


def test_play_in_bracket():
    seeds = [f"T{i}" for i in range(1, 16)]
    even = {t: 0.0 for t in seeds}
    model = {"home_edge": 2.0, "sigma": 12.0}
    assert play_in(seeds, even, model, [5, 5, 5]) == ("T7", "T8")        # home teams win everything
    assert play_in(seeds, even, model, [-5, -5, -5]) == ("T8", "T10")    # road teams win everything
    assert play_in(seeds, even, model, [5, -5, 5]) == ("T7", "T8")       # 7 wins, 10 wins, 8 beats 10


@pytest.fixture(scope="module")
def baseline():
    return Engine(League.load(), load_schedule_2026_27(), load_sim_config(), n_sims=1000).baseline()


def test_every_simulated_season_has_16_playoff_teams_and_full_seeds(baseline):
    assert (baseline["playoff"].sum(axis=1) == 16).all()
    for conf in (EAST, WEST):
        idx = [INDEX[c] for c in conf]
        assert (np.sort(baseline["seeds"][:, idx], axis=1) == np.arange(1, 16)).all()
    assert (baseline["wins"].sum(axis=1) == 1230).all()


def test_summary_columns_are_consistent(baseline):
    for t in baseline["teams"].values():
        assert t["top6_pct"] <= t["playoff_pct"] <= t["top6_pct"] + t["play_in_pct"] + 1e-9
        assert sum(t["seed_frequency"]) == pytest.approx(1.0)
