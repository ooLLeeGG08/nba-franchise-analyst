"""Stage 5: LLM needs and explanations (with a fake LLM), name checks, and the suggestion search."""
import json
from datetime import date

import pytest

from tradesim import ai
from tradesim.checker import check_trade
from tradesim.engine import Engine
from tradesim.games import load_schedule_2026_27
from tradesim.league import League, load_cba
from tradesim.model import load_sim_config
from tradesim.skills import SKILLS, player_skills
from tradesim.suggest import suggest

DATE = date(2026, 11, 9)


class FakeLLM:
    """Returns canned replies in order; records the prompts."""

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def invoke(self, messages):
        self.prompts.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return type("Reply", (), {"content": reply if isinstance(reply, str) else json.dumps(reply)})()


@pytest.fixture(scope="module")
def league():
    return League.load()


@pytest.fixture(scope="module")
def index(league):
    return ai.NameIndex(league.players)


FACTS = {"team": "LAL", "projection": {"mean_wins": 51.7, "playoff_pct": 0.87, "conference_rank": 4},
         "needs": ["Guards"], "team_skills": {s: 50.0 for s in SKILLS} | {"playmaking": 30.0, "rebounding": 35.0},
         "positions": [], "cap": {}, "rotation_ages": []}


# --- names and numbers --------------------------------------------------------------------------

def test_names_ok_only_allows_players_in_the_trade(index):
    allowed = ["derrick-white", "walker-kessler"]
    assert ai.names_ok("The Lakers add Derrick White for Walker Kessler.", allowed, index)
    assert not ai.names_ok("Derrick White pairs well with LeBron James.", allowed, index)
    assert not ai.names_ok("A guard like Jokic would help.", [], index)  # last name alone still counts


def test_numbers_ok_rejects_invented_numbers():
    allowed = [51.7, 53.7, 2.0, 87, 91]
    assert ai.numbers_ok("Wins go from 51.7 to 53.7 (+2.0), playoff odds 87% to 91%.", allowed)
    assert not ai.numbers_ok("He averaged 18.4 points last season.", allowed)


def test_resolver_flags_ambiguous_names(index):
    assert index.resolve("Victor Wembanyama")["status"] == "exact"
    assert index.resolve("Williams")["status"] == "ambiguous"
    assert index.resolve("Not A Player")["status"] == "none"


# --- needs -------------------------------------------------------------------------------------------

def test_needs_without_llm_come_from_data(index):
    n = ai.team_needs(FACTS, index, None)
    assert n["source"] == "data" and n["positions"] == ["G"]
    assert set(n["skills"]) == {"playmaking", "rebounding"}


def test_needs_from_llm_are_validated(index):
    llm = FakeLLM({"timeline": "contend", "positions": ["G", "X"], "skills": ["playmaking", "vibes"],
                   "summary": "Needs a secondary ball handler."})
    n = ai.team_needs(FACTS, index, llm)
    assert n["source"] == "ai" and n["positions"] == ["G"] and n["skills"] == ["playmaking"]
    assert "allowed lists" in n["note"]
    assert "LAL" in llm.prompts[0][1][1] and "Lakers" not in llm.prompts[0][1][1]  # numbers only, no team name


def test_needs_summary_naming_a_player_is_replaced(index):
    llm = FakeLLM({"timeline": "contend", "positions": ["G"], "skills": ["shooting"],
                   "summary": "They should get Stephen Curry."})
    n = ai.team_needs(FACTS, index, llm)
    assert "Curry" not in n["summary"] and "named a player" in n["note"]


def test_needs_llm_failure_falls_back(index):
    n = ai.team_needs(FACTS, index, FakeLLM(RuntimeError("quota")))
    assert n["source"] == "data" and "failed" in n["note"]


# --- explanations ---------------------------------------------------------------------------------------

SHEET = {"team": "LAL", "gets": [{"id": "derrick-white", "name": "Derrick White", "position": "G", "impact": 2.3, "salary_m": 30.3}],
         "sends": [{"id": "walker-kessler", "name": "Walker Kessler", "position": "C", "impact": 2.1, "salary_m": 30.1}],
         "picks": [], "wins_before": 51.7, "wins_after": 53.7, "win_change": 2.0, "playoff_before": 87,
         "playoff_after": 91, "playoff_change": 4, "skills_needed": ["playmaking"]}


def test_explanations_are_checked(index):
    llm = FakeLLM({"explanations": [
        "Derrick White adds playmaking; wins rise from 51.7 to 53.7.",
        "Pairing White with Anthony Davis lifts them to 53.7 wins.",
        "White averaged 15.2 points last year, lifting wins to 53.7."]})
    out = ai.explain([SHEET, SHEET, SHEET], index, llm)
    assert [o["source"] for o in out] == ["ai", "template", "template"]
    assert all("Davis" not in o["text"] and "15.2" not in o["text"] for o in out)


def test_explanations_without_llm_use_template(index):
    out = ai.explain([SHEET], index, None)
    assert out[0]["source"] == "template" and "51.7 -> 53.7" in out[0]["text"]


# --- the search -----------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def result(league):
    engine = Engine(league, load_schedule_2026_27(), load_sim_config(), n_sims=1000)
    return suggest("LAL", engine, league, load_cba(), DATE), engine


def test_suggestions_are_legal_and_use_database_players(result, league):
    r, _ = result
    cba = load_cba()
    assert 1 <= len(r["suggestions"]) <= 4
    for s in r["suggestions"]:
        assert check_trade(league, cba, {"moves": s["moves"]}, DATE)["works"]
        for p in s["gets"] + s["sends"]:
            assert league.players[p["id"]]["name"] == p["name"]
        assert all(m["from"] in ("LAL", s["partner"]) and m["to"] in ("LAL", s["partner"]) for m in s["moves"])


def test_suggestions_respect_realism_rules_and_variety(result):
    r, _ = result
    rules = r["rules"]
    gets = [s["gets"][0]["id"] for s in r["suggestions"]]
    assert len(gets) == len(set(gets))
    partners = [s["partner"] for s in r["suggestions"]]
    assert all(partners.count(p) <= 2 for p in partners)
    for s in r["suggestions"]:
        assert s["win_change"] >= rules["min_win_gain"] - 0.05
        assert s["partner_win_change"] >= -rules["max_partner_loss_wins"] - 0.05
    changes = [s["win_change"] for s in r["suggestions"]]
    assert changes == sorted(changes, reverse=True)


def test_suggestions_fill_a_needed_position(result, league):
    r, _ = result
    from tradesim.rotation import buckets
    wanted = {{"G": 0, "F": 1, "C": 2}[p] for p in r["needs"]["positions"]}
    for s in r["suggestions"]:
        assert buckets(s["gets"][0]["position"]) & wanted
        fit = sum(player_skills(league.players[s["gets"][0]["id"]]).get(k, 0) for k in r["needs"]["skills"]) / len(r["needs"]["skills"])
        assert fit >= 55


def test_suggestions_endpoint_and_cache(tmp_path, monkeypatch):
    import server
    import tradesim.engine as eng
    monkeypatch.setattr(eng, "CACHE_DIR", str(tmp_path))
    client = server.app.test_client()
    assert client.get("/api/sim/team/XYZ/suggestions").status_code == 404
    first = client.get("/api/sim/team/BKN/suggestions").get_json()
    second = client.get("/api/sim/team/BKN/suggestions").get_json()
    assert first["from_cache"] is False and second["from_cache"] is True
    assert first["suggestions"] == second["suggestions"]
    r = client.get("/api/sim/players/resolve?q=williams").get_json()
    assert r["status"] == "ambiguous" and all("name" in p for p in r["players"])


def test_lone_last_names(index):
    assert ai.names_ok("White's playmaking is the fit here.", ["derrick-white", "walker-kessler"], index)
    assert not ai.names_ok("Williams would also help.", ["derrick-white"], index)  # which Williams?
