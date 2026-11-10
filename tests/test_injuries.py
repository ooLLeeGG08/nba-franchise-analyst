"""Long-term injury override tests (config/long_injuries.json)."""
import json

import pytest

from tradesim import ratings
from tradesim.league import player_id, League
from tradesim.model import load_sim_config
from tradesim.names import name_key
from tradesim.ratings import games_after, injury_availability, load_long_injuries, load_ratings


@pytest.fixture(scope="module")
def schedule():
    with open(f"{ratings.ROOT}/data/raw/2026_27/schedule.json") as f:
        return json.load(f)["games"]


def test_file_has_required_fields_and_only_long_absences(schedule):
    inj = load_long_injuries()
    assert inj["as_of"] and inj["min_games_out"] == 15
    league = League.load()
    for e in inj["injuries"]:
        assert {"player", "team", "source_url", "date_added"} <= set(e)
        assert ("return_date" in e) != ("games_out" in e)
        assert league.players[e["player"]]["team"] == e["team"]
        out = games_after(e["team"], inj["as_of"], schedule) - games_after(e["team"], e["return_date"], schedule)
        assert out >= 15, e["player"]


def test_finished_overtime_games_count_as_played(schedule):
    final_ot = [g for g in schedule if g["status"] == "Final/OT"]
    assert final_ot
    g = final_ot[0]
    assert games_after(g["home"], g["date"], [g]) == 0


def test_override_replaces_availability_without_double_counting():
    r = load_ratings()["players"][player_id("chet-holmgren")]
    li = r["long_injury"]
    # Games he already played + games after his return x his normal availability, over 82.
    assert r["availability"] == pytest.approx(li["expected_games_played"] / 82, abs=0.002)
    assert li["games_out"] >= 15
    assert r["games_2026_27"] + li["games_out"] + li["games_after_return"] <= 82


def test_short_absences_are_rejected():
    inj = {"as_of": "2026-11-09", "min_games_out": 15}
    entry = {"player": "x", "team": "OKC", "games_out": 5}
    games = [{"home": "OKC", "away": "BOS", "date": f"2026-12-{d:02d}", "status": "7:00 pm"} for d in range(1, 21)]
    with pytest.raises(ValueError, match="15\\+"):
        injury_availability(entry, {"team": "OKC"}, 0, 0.8, inj, games)


def test_unlisted_players_keep_their_sampled_availability():
    cfg = load_sim_config()
    fit = ratings.load_fit()
    rated = load_ratings()["players"]
    listed = {e["player"] for e in load_long_injuries()["injuries"]}
    league = League.load()
    for pid in (player_id("nikola-jokic"), player_id("tyrese-haliburton"), player_id("jaren-jackson")):
        assert pid not in listed
        expected = ratings.availability(league.players[pid]["bbref_id"], ratings.CURRENT_SEASON, fit, cfg,
                                        games_now=rated[pid]["games_2026_27"])
        assert rated[pid]["availability"] == pytest.approx(expected, abs=0.001)
        assert rated[pid]["long_injury"] is None


def test_affected_teams_are_flagged_in_the_season_table():
    from tradesim.simulate import season_table
    rows = {r["team"]: r for r in season_table()}
    teams = set(load_ratings()["long_injury_teams"])
    assert teams == {e["team"] for e in load_long_injuries()["injuries"]}
    assert all(rows[c]["injury_adjusted"] == (c in teams) for c in rows)
