"""Cap checker tests on real 2026-27 players and salaries.

All trades are checked as of Nov 9, 2026 unless a test says otherwise.
The first two are the user's own examples (Fanspo trade machine, Nov 9, 2026).
"""
import pytest

from tradesim.checker import (FAIL, NOT_CHECKED, PASS, check_trade, check_trades_in_sequence,
                              max_incoming)
from tradesim.league import League, load_cba

DATE = "2026-11-09"


@pytest.fixture(scope="module")
def league():
    return League.load()


@pytest.fixture(scope="module")
def cba():
    return load_cba()


def player(pid, frm, to):
    return {"type": "player", "id": pid, "from": frm, "to": to}


def pick(pid, frm, to):
    return {"type": "pick", "id": pid, "from": frm, "to": to}


def cash(amount, frm, to):
    return {"type": "cash", "amount": amount, "from": frm, "to": to}


def rule(result, team, rule_id):
    return next(r for r in result["teams"][team]["rules"] if r["id"] == rule_id)


# --- the user's two real examples --------------------------------------------------

def test_maxey_for_johnson_and_wiggins_works(league, cba):
    """Fanspo: SUCCESS, both teams pass."""
    r = check_trade(league, cba, {"moves": [player("tyrese-maxey", "PHI", "ATL"),
                                            player("jalen-johnson", "ATL", "PHI"),
                                            player("aaron-wiggins", "ATL", "PHI")]}, DATE)
    assert r["works"], r["teams"]["ATL"]["failures"] + r["teams"]["PHI"]["failures"]
    assert rule(r, "ATL", "salary_matching")["status"] == PASS
    assert rule(r, "ATL", "aggregation")["status"] == PASS  # Wiggins acquired Jul 6, > 60 days ago
    assert r["teams"]["ATL"]["salary_after"] - r["teams"]["ATL"]["salary_before"] == 40_770_520 - 38_831_776


def test_embiid_for_johnson_fails_for_hawks(league, cba):
    """Fanspo: FAILED, 'Takes in $28.0M more than the 2nd apron allows.' 76ers pass."""
    r = check_trade(league, cba, {"moves": [player("joel-embiid", "PHI", "ATL"),
                                            player("jalen-johnson", "ATL", "PHI")]}, DATE)
    assert not r["works"]
    assert r["teams"]["PHI"]["works"]
    matching = rule(r, "ATL", "salary_matching")
    assert matching["status"] == FAIL
    assert "$28.0M more" in matching["detail"] and "second apron" in matching["detail"]
    assert rule(r, "ATL", "hard_cap")["status"] == FAIL  # hard-capped at the first apron since the offseason
    assert rule(r, "ATL", "trade_exception")["status"] == FAIL  # can't use exceptions above the second apron


# --- salary matching ------------------------------------------------------------------

def test_max_incoming_tiers_come_from_config(cba):
    assert max_incoming(5_000_000, cba) == 5_000_000 * 2 + 250_000
    assert max_incoming(9_096_000, cba) == 9_096_000 * 2 + 250_000
    assert max_incoming(20_000_000, cba) == 20_000_000 + 9_096_000
    assert max_incoming(40_000_000, cba) == 40_000_000 * 1.25 + 250_000


def test_middle_tier_trade_works(league, cba):
    # Hornets send Brandon Miller ($15.1M): can take back up to $24.2M. Jabari Smith is $23.6M.
    r = check_trade(league, cba, {"moves": [player("brandon-miller", "CHA", "HOU"),
                                            player("jabari-smith", "HOU", "CHA")]}, DATE)
    assert r["works"]
    assert rule(r, "CHA", "trade_exception")["detail"] == "No exception needed."


def test_taking_back_too_much_salary_fails(league, cba):
    # Blazers send Shaedon Sharpe ($20.1M): max back $29.2M. Derrick White is $30.3M.
    r = check_trade(league, cba, {"moves": [player("shaedon-sharpe", "POR", "BOS"),
                                            player("derrick-white", "BOS", "POR")]}, DATE)
    assert not r["works"]
    assert rule(r, "POR", "salary_matching")["status"] == FAIL
    assert "$1.2M more than salary matching allows" in rule(r, "POR", "salary_matching")["detail"]
    # Portland has no exception in the data, so that rule is "not checked", never a silent pass.
    assert rule(r, "POR", "trade_exception")["status"] == NOT_CHECKED
    assert r["teams"]["BOS"]["works"]


def test_team_under_cap_absorbs_into_room(league, cba):
    # Nets are $4.9M under the cap; taking on $1.5M net fits.
    r = check_trade(league, cba, {"moves": [player("danny-wolf", "BKN", "MIN"),
                                            player("joan-beringer", "MIN", "BKN")]}, DATE)
    assert r["works"]
    assert "under the cap" in rule(r, "BKN", "salary_matching")["detail"]


# --- aprons and hard caps ----------------------------------------------------------------

def test_second_apron_team_cannot_combine_salaries(league, cba):
    # Nuggets ($224.3M) send two players for one, still ending above the second apron.
    r = check_trade(league, cba, {"moves": [player("zeke-nnaji", "DEN", "GSW"),
                                            player("spencer-jones", "DEN", "GSW"),
                                            player("moses-moody", "GSW", "DEN")]}, DATE)
    assert rule(r, "DEN", "second_apron")["status"] == FAIL
    assert "combine salaries" in rule(r, "DEN", "second_apron")["detail"]


def test_cash_limits(league, cba):
    base = [player("brandon-miller", "CHA", "HOU"), player("jabari-smith", "HOU", "CHA")]
    over = check_trade(league, cba, {"moves": base + [cash(9_000_000, "HOU", "CHA")]}, DATE)
    assert rule(over, "HOU", "cash")["status"] == FAIL
    ok = check_trade(league, cba, {"moves": base + [cash(2_000_000, "HOU", "CHA")]}, DATE)
    # Within the limit, but earlier cash this season isn't tracked -> not checked, not pass.
    assert rule(ok, "HOU", "cash")["status"] == NOT_CHECKED


def test_cash_from_second_apron_team_fails(league, cba):
    r = check_trade(league, cba, {"moves": [player("tyus-jones", "DEN", "NYK"),
                                            player("jordan-clarkson", "NYK", "DEN"),
                                            cash(1_000_000, "DEN", "NYK")]}, DATE)
    assert rule(r, "DEN", "second_apron")["status"] == FAIL
    assert "send cash" in rule(r, "DEN", "second_apron")["detail"]


# --- trade exceptions ----------------------------------------------------------------------

def test_trade_exception_absorbs_player(league, cba):
    # Hornets send a $2.5M player for Christian Braun ($21.6M): plain matching fails,
    # but the $40.8M LaMelo Ball exception absorbs Braun.
    r = check_trade(league, cba, {"moves": [player("moussa-diabate", "CHA", "DEN"),
                                            player("christian-braun", "DEN", "CHA")]}, DATE)
    assert r["works"], r["teams"]["CHA"]["failures"]
    assert r["teams"]["CHA"]["exception_used"] == {"id": "TPE-CHA-lamelo-ball", "player": "christian-braun"}
    assert "LaMelo Ball exception" in rule(r, "CHA", "trade_exception")["detail"]


def test_expired_trade_exception_cannot_be_used(league, cba):
    # Memphis's Jaren Jackson Jr. exception expires Feb 3, 2027.
    moves = {"moves": [player("olivier-maxence-prosper", "MEM", "DEN"), player("christian-braun", "DEN", "MEM")]}
    before = check_trade(league, cba, moves, "2027-01-20")
    assert before["teams"]["MEM"]["exception_used"]["id"] == "TPE-MEM-jaren-jackson"
    after = check_trade(league, cba, moves, "2027-02-04")
    assert not after["teams"]["MEM"]["works"]
    assert "expired" in rule(after, "MEM", "trade_exception")["detail"]


# --- player restrictions -----------------------------------------------------------------------

def test_recently_signed_player_dates(league, cba):
    # Anfernee Simons signed Jul 6, 2026: not tradeable before Dec 15.
    moves = {"moves": [player("anfernee-simons", "PHI", "NYK"), player("jordan-clarkson", "NYK", "PHI")]}
    assert rule(check_trade(league, cba, moves, DATE), "PHI", "recently_signed")["status"] == FAIL
    # Dec 15 - Jan 14: allowed unless he re-signed with a 20%+ raise, which the data can't tell.
    assert rule(check_trade(league, cba, moves, "2026-12-20"), "PHI", "recently_signed")["status"] == NOT_CHECKED
    assert rule(check_trade(league, cba, moves, "2027-01-20"), "PHI", "recently_signed")["status"] == PASS


def test_no_trade_clause_fails_the_trade(league, cba):
    r = check_trade(league, cba, {"moves": [player("damian-lillard", "POR", "BOS"),
                                            player("derrick-white", "BOS", "POR")]}, DATE)
    assert rule(r, "POR", "no_trade")["status"] == FAIL
    assert not r["teams"]["POR"]["works"]
    assert "no-trade clause" in rule(r, "POR", "no_trade")["detail"]


def test_bird_veto_is_flagged(league, cba):
    r = check_trade(league, cba, {"moves": [player("al-horford", "GSW", "NYK"),
                                            player("landry-shamet", "NYK", "GSW")]}, DATE)
    assert rule(r, "GSW", "no_trade")["status"] == FAIL


def test_cannot_reacquire_player_traded_away_this_season(league, cba):
    # Charlotte traded LaMelo Ball to Minnesota on Jul 10, 2026.
    r = check_trade(league, cba, {"moves": [player("lamelo-ball", "MIN", "CHA"),
                                            player("brandon-miller", "CHA", "MIN"),
                                            player("kon-knueppel", "CHA", "MIN"),
                                            player("tidjane-salaun", "CHA", "MIN")]}, DATE)
    assert rule(r, "CHA", "reacquire")["status"] == FAIL


def test_extensions_are_never_silently_passed(league, cba):
    r = check_trade(league, cba, {"moves": [player("brandon-miller", "CHA", "HOU"),
                                            player("jabari-smith", "HOU", "CHA")]}, DATE)
    assert rule(r, "CHA", "extensions")["status"] == NOT_CHECKED


# --- roster size --------------------------------------------------------------------------------

def test_roster_must_end_between_14_and_15(league, cba):
    # Two-for-one leaves the Nuggets (14) at 13.
    r = check_trade(league, cba, {"moves": [player("zeke-nnaji", "DEN", "GSW"),
                                            player("spencer-jones", "DEN", "GSW"),
                                            player("moses-moody", "GSW", "DEN")]}, DATE)
    assert rule(r, "DEN", "roster_size")["status"] == FAIL
    assert rule(r, "GSW", "roster_size")["status"] == FAIL  # 15 -> 16


# --- draft picks ----------------------------------------------------------------------------------

def test_frozen_pick_cannot_be_traded(league, cba):
    r = check_trade(league, cba, {"moves": [pick("BOS-2032-R1-0", "BOS", "BKN"),
                                            player("danny-wolf", "BKN", "BOS")]}, DATE)
    assert rule(r, "BOS", "pick_ownership")["status"] == FAIL


def test_stepien_rule(league, cba):
    # The Knicks' 2029 first already belongs to Brooklyn; sending their 2030 first too would
    # leave no first in back-to-back drafts.
    r = check_trade(league, cba, {"moves": [pick("NYK-2030-R1-0", "NYK", "BKN"),
                                            player("danny-wolf", "BKN", "NYK"),
                                            player("jordan-clarkson", "NYK", "BKN")]}, DATE)
    assert rule(r, "NYK", "stepien")["status"] == FAIL
    assert "2029 and 2030" in rule(r, "NYK", "stepien")["detail"]


def test_sending_a_pick_you_dont_hold_is_rejected(league, cba):
    r = check_trade(league, cba, {"moves": [pick("NYK-2030-R1-0", "ATL", "BKN"),
                                            player("danny-wolf", "BKN", "ATL")]}, DATE)
    assert not r["works"]
    assert any("doesn't hold" in e for e in r["errors"])


def test_conditional_picks_are_marked_not_checked(league, cba):
    conditional = next(p for p in league.picks.values() if p["holder"] == "BKN" and p["kind"] == "conditional")
    r = check_trade(league, cba, {"moves": [pick(conditional["id"], "BKN", "MIN"),
                                            player("danny-wolf", "BKN", "MIN"),
                                            player("joan-beringer", "MIN", "BKN")]}, DATE)
    assert rule(r, "BKN", "pick_protections")["status"] == NOT_CHECKED


# --- structure and multi-trade sequences -------------------------------------------------------------

def test_same_player_twice_in_one_trade_is_rejected(league, cba):
    r = check_trade(league, cba, {"moves": [player("danny-wolf", "BKN", "MIN"),
                                            player("danny-wolf", "BKN", "MIN")]}, DATE)
    assert any("appears twice" in e for e in r["errors"])


def test_waived_player_cannot_be_traded(league, cba):
    r = check_trade(league, cba, {"moves": [player("blake-wesley", "LAC", "BKN"),
                                            player("danny-wolf", "BKN", "LAC")]}, DATE)
    assert any("waived" in e for e in r["errors"])


def test_three_team_trade_checks_every_team(league, cba):
    r = check_trade(league, cba, {"moves": [player("brandon-miller", "CHA", "HOU"),
                                            player("jabari-smith", "HOU", "BKN"),
                                            player("danny-wolf", "BKN", "CHA")]}, DATE)
    assert set(r["teams"]) == {"CHA", "HOU", "BKN"}
    assert all(len(t["rules"]) == 14 for t in r["teams"].values())


def test_sequence_blocks_using_the_same_player_twice(league, cba):
    maxey = {"moves": [player("tyrese-maxey", "PHI", "ATL"), player("jalen-johnson", "ATL", "PHI"),
                       player("aaron-wiggins", "ATL", "PHI")]}
    again = {"moves": [player("jalen-johnson", "ATL", "BOS"), player("derrick-white", "BOS", "ATL")]}
    results, _ = check_trades_in_sequence(league, cba, [maxey, again], DATE)
    assert results[0]["works"]
    assert not results[1]["works"]
    assert any("moved there in trade 1" in e for e in results[1]["errors"])


def test_sequence_uses_payroll_left_by_previous_trade(league, cba):
    maxey = {"moves": [player("tyrese-maxey", "PHI", "ATL"), player("jalen-johnson", "ATL", "PHI"),
                       player("aaron-wiggins", "ATL", "PHI")]}
    # Philadelphia then combines the two players it just received: they arrived today, so
    # their salaries can't be combined for 60 days.
    flip = {"moves": [player("jalen-johnson", "PHI", "BOS"), player("aaron-wiggins", "PHI", "BOS"),
                      player("derrick-white", "BOS", "PHI")]}
    results, final = check_trades_in_sequence(league, cba, [maxey, flip], DATE)
    assert results[1]["teams"]["PHI"]["salary_before"] == results[0]["teams"]["PHI"]["salary_after"]
    assert rule(results[1], "PHI", "aggregation")["status"] == FAIL
    # The original league is untouched.
    assert league.players["tyrese-maxey"]["team"] == "PHI"
    assert final.players["tyrese-maxey"]["team"] == "ATL"


def test_failed_trade_in_sequence_is_not_applied(league, cba):
    embiid = {"moves": [player("joel-embiid", "PHI", "ATL"), player("jalen-johnson", "ATL", "PHI")]}
    maxey = {"moves": [player("tyrese-maxey", "PHI", "ATL"), player("jalen-johnson", "ATL", "PHI"),
                       player("aaron-wiggins", "ATL", "PHI")]}
    results, _ = check_trades_in_sequence(league, cba, [embiid, maxey], DATE)
    assert not results[0]["works"]
    assert results[1]["works"]


def test_apron_percentage_is_read_from_config(league, cba):
    """Regression: the above-first-apron limit must come from the config, not be assumed to be 100%."""
    import copy
    loose = copy.deepcopy(cba)
    loose["salary_matching"]["max_percent_above_first_apron"] = 2.0
    r = check_trade(league, loose, {"moves": [player("joel-embiid", "PHI", "ATL"),
                                              player("jalen-johnson", "ATL", "PHI")]}, DATE)
    assert rule(r, "ATL", "salary_matching")["status"] == PASS
