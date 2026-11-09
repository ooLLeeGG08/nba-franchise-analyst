"""Data layer tests: the raw-file parsers and the built league.json."""
import json

import pytest

from tradesim import build_data
from tradesim.league import League, load_cba
from tradesim.names import name_key
from tradesim.picks import _split_top_level, classify, parse_picks_text


@pytest.fixture(scope="module")
def league():
    return League.load()


def test_name_key_matches_spellings_across_sources():
    assert name_key("Nikola Jokić") == name_key("Nikola Jokic")
    assert name_key("R.J. Barrett") == name_key("RJ Barrett")
    assert name_key("Jaren Jackson Jr.") == "jaren jackson"
    assert name_key("Herb Jones") == name_key("Herbert Jones")


def test_parse_contracts_handles_uneven_blank_lines():
    text = "PLAYER\nTEAM\n2026-27 SALARY\n% OF CAP\n1\nStephen Curry\n\nGolden State Warriors\n$62,587,158\n37.9%\n" \
           "2\nJosh Giddey\n\n\nChicago Bulls\n$25,000,000\n15.2%\n"
    rows = build_data.parse_contracts(text)
    assert rows == [{"rank": 1, "name": "Stephen Curry", "team": "GSW", "salary": 62_587_158},
                    {"rank": 2, "name": "Josh Giddey", "team": "CHI", "salary": 25_000_000}]


def test_parse_fixed_width_stats_with_stints_and_blanks():
    def line(rk, name, age, team, pos, g, gs, mp, ts, bpm, vorp):
        return f"{rk:>3}  {name:<26}{age:>3}  {team:<4}  {pos:<3} {g:>3} {gs:>3} {mp:>5} {ts:>5} {bpm:>6} {vorp:>5}"
    text = "\n".join([
        line("Rk", "Player", "Age", "Team", "Pos", "G", "GS", "MP", "TS%", "BPM", "VORP"),
        "-" * 80,
        line("17", "Zach LaVine", "29", "2TM", "SG", "74", "74", "2602", ".639", "0.7", "1.8"),
        line("", "      CHI stint", "29", "CHI", "SF", "42", "42", "1432", ".637", "1.6", "1.3"),
        line("569", "Jahlil Okafor", "29", "IND", "C", "1", "0", "3", "", "7.5", "0.0"),
    ])
    rows = list(build_data._fixed_width_rows(text))
    assert [(r["Player"], r["Team"], r["MP"]) for r in rows] == [
        ("Zach LaVine", "2TM", "2602"), ("Zach LaVine", "CHI", "1432"), ("Jahlil Okafor", "IND", "3")]
    assert rows[2]["TS%"] == "" and rows[2]["BPM"] == "7.5"


def test_2024_25_stats_cover_injured_stars(league):
    for pid in ("tyrese-haliburton", "damian-lillard", "kyrie-irving", "fred-vanvleet"):
        assert league.players[pid]["stats_2025_26"] is None
        assert league.players[pid]["stats_2024_25"]["mp"] > 1500


def test_parse_how_acquired():
    assert build_data.parse_how_acquired("Signed on 07/06/26") == {"type": "signed", "date": "2026-07-06"}
    assert build_data.parse_how_acquired("Traded from CHA on 07/10/26") == {
        "type": "traded", "from_team": "CHA", "date": "2026-07-10"}
    assert build_data.parse_how_acquired("#1 Pick in 2026 Draft") == {"type": "draft", "pick": 1, "draft_year": 2026}
    assert build_data.parse_how_acquired(None) == {"type": "unknown"}


def test_pick_text_splitting_and_classification():
    assert _split_top_level("Own; NYK (via POR; via DAL)") == ["Own", "NYK (via POR; via DAL)"]
    assert classify("Own") == ("own", None)
    assert classify("NYK (via POR)") == ("acquired", "NYK")
    assert classify("To SAN") == ("conveyed", "SAS")
    assert classify("Frozen (through 2027-28)") == ("frozen", None)
    assert classify("Less favorable of MIL and NOP if either or both 5-30 (via NOP)")[0] == "conditional"


def test_parse_picks_second_round_count_prefix():
    text = "--- ATLANTA HAWKS ---\nYear 2030:\n  First Round: Own\n  Second Round: 1; To OKC; NYK (via POR)\n"
    entries = parse_picks_text(text)
    assert [(e["round"], e["kind"], e["original_team"]) for e in entries] == [
        (1, "own", "ATL"), (2, "conveyed", None), (2, "acquired", "NYK")]


def test_league_has_every_team_and_player(league):
    assert len(league.teams) == 30
    assert len(league.players) == 434
    assert sum(1 for p in league.players.values() if not p["on_roster"]) == 1  # Blake Wesley, waived


def test_payroll_matches_user_cap_sheet(league):
    sheet = json.load(open(f"{build_data.RAW}/cap_sheet.json"))["teams"]
    for code, team in league.teams.items():
        assert abs(team["payroll"] / 1e6 - sheet[team["name"]]["payroll"]) < 0.051, code


def test_team_salary_matches_cap_sheet_apron_room(league):
    cba = load_cba()
    sheet = json.load(open(f"{build_data.RAW}/cap_sheet.json"))["teams"]
    for code, team in league.teams.items():
        implied = cba["first_apron"] - sheet[team["name"]]["apron1_room"] * 1e6
        assert abs(team["team_salary"] - implied) <= 100_000, code


def test_first_round_rookies_have_salaries(league):
    rookies = [p for p in league.players.values()
               if p["acquired"].get("type") == "draft" and p["acquired"].get("draft_year") == 2026
               and p["acquired"]["pick"] <= 30]
    assert len(rookies) >= 20
    assert all(p["salary"] > 2_000_000 for p in rookies)


def test_no_trade_data_applied_to_current_team(league):
    assert league.players["damian-lillard"]["team"] == "POR"
    assert league.players["damian-lillard"]["no_trade_clause"]
    assert league.players["al-horford"]["bird_veto"]


def test_trade_exceptions_parsed(league):
    e = league.trade_exceptions["TPE-OKC-luguentz-dort"]
    assert (e["team"], e["amount"], e["expires"], e["prior_season"]) == ("OKC", 17_722_222, "2027-07-19", False)
    assert league.trade_exceptions["TPE-MEM-jaren-jackson"]["prior_season"]


def test_built_file_is_up_to_date():
    """league.json must be rebuilt after editing a raw file: python -m tradesim.build_data"""
    fresh = json.loads(json.dumps(build_data.build(write=False), ensure_ascii=False))
    stored = json.load(open(build_data.OUT))
    for key in ("teams", "players", "picks", "trade_exceptions", "calendar", "build_report"):
        assert fresh[key] == stored[key], f"{key} is stale; run python -m tradesim.build_data"
