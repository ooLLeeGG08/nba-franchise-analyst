"""Stage 5: LLM needs and explanations (with a fake LLM), name checks, and the suggestion search."""
import json
from datetime import date

import pytest

from tradesim import ai
from tradesim.checker import check_trade
from tradesim.engine import Engine
from tradesim.games import load_schedule_2026_27
from tradesim.league import player_id, League, load_cba
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
    allowed = [player_id("derrick-white"), player_id("walker-kessler")]
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

SHEET = {"team": "LAL", "gets": [{"id": player_id("derrick-white"), "name": "Derrick White", "position": "G", "impact": 2.3, "salary_m": 30.3,
                                  "from": "BOS", "to": "LAL"}],
         "sends": [{"id": player_id("walker-kessler"), "name": "Walker Kessler", "position": "C", "impact": 2.1, "salary_m": 30.1,
                    "from": "LAL", "to": "BOS"}],
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


@pytest.mark.parametrize("text, ok", [
    ("Derrick White adds playmaking; wins rise from 51.7 to 53.7.", True),
    # a number tied to a player must be his (2.1 is Kessler's impact, not White's)
    ("Derrick White, rated +2.1, lifts wins to 53.7.", False),
    ("Derrick White, rated +2.3, lifts wins to 53.7.", True),
    ("Walker Kessler (+2.1) heads out.", True),
    # numbers from league.json / the ratings file for that player are fine
    ("Derrick White, 32, comes from Boston.", True),
    ("Derrick White earns 30.3M.", True),
    ("Derrick White earns 41.0M.", False),
    # a team tied to a player must be his team or where the trade sends him
    ("Derrick White leaves Boston for the Lakers.", True),
    ("Derrick White joins from the Heat.", False),
    ("BOS sends White to LAL.", True),
    ("Kessler goes to the Celtics.", True),
    ("Kessler goes to the Knicks.", False),
    # no player named: teams must be in the trade
    ("The Lakers gain 2.0 wins.", True),
    ("The Lakers pass the Nuggets with 53.7 wins.", False),
    # lowercase words that are also team names aren't teams
    ("White brings heat and a little magic; 53.7 wins.", True),
    # possessives and accents: "Jokić's" is Nikola Jokic, who isn't in this trade
    ("With Jokić's spacing gone, wins reach 53.7.", False),
    ("Derrick White's playmaking lifts wins to 53.7.", True),
    # two sentences: the second sentence's number is checked on its own
    ("Derrick White joins. Wins rise to 53.7.", True),
    ("Derrick White joins. Wins rise to 58.0.", False),
])
def test_facts_check(text, ok, index):
    assert ai.facts_ok(text, SHEET, index)[0] is ok, ai.facts_ok(text, SHEET, index)


def test_accents_and_suffixes_match(index, league):
    """Names match without accents or suffixes, both ways."""
    sheet = {"team": "BKN", "gets": [], "picks": [], "wins_before": 30.0, "wins_after": 31.0, "win_change": 1.0,
             "playoff_before": 5, "playoff_after": 6, "playoff_change": 1,
             "sends": [{"id": player_id("egor-demin"), "name": "Egor Dëmin", "position": "G", "impact": 0.0, "salary_m": 5.0,
                        "from": "BKN", "to": "BOS"}]}
    for spelling in ("Egor Dëmin", "Egor Demin", "EGOR DEMIN", "Demin's"):
        assert ai.facts_ok(f"{spelling} heads to Boston.", sheet, index)[0], spelling
    pj = next(pid for pid, p in league.players.items() if p["name"] == "P.J. Washington")
    sheet["sends"][0].update(id=pj, name="P.J. Washington", **{"from": league.players[pj]["team"]})
    sheet["team"] = league.players[pj]["team"]
    assert ai.facts_ok("P.J. Washington heads to Boston.", sheet, index)[0]  # not "Washington" the team
    jjj = next(pid for pid, p in league.players.items() if p["name"].startswith("Jaren Jackson"))
    assert index.mentioned("Jaren Jackson Jr. and Jaren Jackson")[0] == {jjj}


def test_templates_pass_their_own_check(result, index):
    """Every template sentence for real suggestions passes the same check the LLM faces."""
    r, _ = result
    for sg in r["suggestions"]:
        assert sg["explanation"]["source"] == "template"
        sheet = {"team": "LAL", "partner": sg["partner"], "picks": [{"label": p["label"], "year": p["year"]} for p in sg["picks_out"]],
                 "gets": [{**g, "from": sg["partner"], "to": "LAL"} for g in sg["gets"]],
                 "sends": [{**x, "from": "LAL", "to": sg["partner"]} for x in sg["sends"]],
                 "wins_before": round(sg["wins_before"], 1), "wins_after": round(sg["wins_after"], 1),
                 "win_change": sg["win_change"], "playoff_before": round(sg["playoff_before"] * 100),
                 "playoff_after": round(sg["playoff_after"] * 100),
                 "playoff_change": round((sg["playoff_after"] - sg["playoff_before"]) * 100)}
        assert ai.facts_ok(sg["explanation"]["text"], sheet, index) == (True, None), sg["explanation"]["text"]


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


def test_suggestions_say_how_well_they_fit(result, league):
    """'fits the need' = needed position and 55th+ percentile in the needed skills; looser
    matches are labelled."""
    r, _ = result
    from tradesim.rotation import buckets
    wanted = {{"G": 0, "F": 1, "C": 2}[p] for p in r["needs"]["positions"]}
    for s in r["suggestions"]:
        assert s["match"] in ("fits the need", "partial fit", "best available upgrade")
        fit = sum(player_skills(league.players[s["gets"][0]["id"]]).get(k, 0) for k in r["needs"]["skills"]) / len(r["needs"]["skills"])
        if s["match"] == "fits the need":
            assert buckets(s["gets"][0]["position"]) & wanted and fit >= 55
        elif s["match"] == "partial fit":
            assert fit >= 40


def test_center_need_gets_center_skills(league):
    """A team short at center is asked for center skills (vs other teams' centers), not its
    weakest skills overall."""
    facts = {"needs": ["Centers"], "projection": {"playoff_pct": 0.6},
             "team_skills": {s: 50.0 for s in SKILLS} | {"shooting": 10.0},
             "position_skills": {g: {s: 50.0 for s in SKILLS} for g in "GFC"},
             "league_position_skills": {g: {s: 50.0 for s in SKILLS} for g in "GFC"}}
    facts["position_skills"]["C"].update({"rim protection": 30.0, "rebounding": 35.0})
    needs = ai.data_needs(facts)
    assert needs["positions"] == ["C"] and set(needs["skills"]) == {"rim protection", "rebounding"}


def test_short_roster_team_can_still_get_ideas(result, league):
    """Teams below 14 contracts must take back more players than they send; a filler player
    from the partner makes that possible (Sacramento has 13)."""
    from tradesim.suggest import SearchState, _packages, find_candidates
    _, engine = result
    cba = load_cba()
    state = SearchState(engine, league)
    needs = {"positions": ["G", "F", "C"], "skills": ["scoring"]}
    cands = find_candidates("SAC", needs, state, cba, DATE, min_fit=0)
    pkgs = [p for c in cands for p in _packages("SAC", c, state, cba, DATE, None)]
    assert pkgs and all(len(extra) == 1 for _, _, _, extra in pkgs)


def _engine_with_reuse(engine, reuse):
    import copy
    e = copy.copy(engine)
    e.cfg = copy.deepcopy(engine.cfg)
    e.cfg["suggestions"]["max_asset_reuse"] = reuse
    return e


@pytest.fixture(scope="module")
def diverse(result, league):
    """LAL with diversity on (max_asset_reuse = 1), whatever the config says."""
    return suggest("LAL", _engine_with_reuse(result[1], 1), league, load_cba(), DATE)


def test_no_asset_appears_in_two_suggestions(diverse):
    """Diversity (max_asset_reuse = 1): no outgoing player or pick appears in more than one of
    the 4 suggestions, so any of them can be combined."""
    r = diverse
    assert r["rules"]["max_asset_reuse"] == 1
    outgoing = [m["id"] for s in r["suggestions"] for m in s["moves"] if m["from"] == "LAL"]
    assert len(outgoing) == len(set(outgoing))
    every = [m["id"] for s in r["suggestions"] for m in s["moves"] if m["type"] != "cash"]
    assert len(every) == len(set(every))  # incoming fillers aren't shared either


@pytest.mark.parametrize("code", ["BOS", "ATL"])
def test_diversity_holds_for_teams_that_used_to_repeat(code, result, league):
    """Boston's list used to put Ron Harper Jr. in 3 of 4 ideas and the same 2nd in 3 of 4."""
    r = suggest(code, _engine_with_reuse(result[1], 1), league, load_cba(), DATE)
    outgoing = [m["id"] for s in r["suggestions"] for m in s["moves"] if m["from"] == code]
    assert len(r["suggestions"]) == 4 and len(outgoing) == len(set(outgoing))


def test_reuse_limit_two(result, league):
    """max_asset_reuse = 2: no player or pick in more than two ideas."""
    from collections import Counter
    r = suggest("BKN", _engine_with_reuse(result[1], 2), league, load_cba(), DATE)
    use = Counter(m["id"] for s in r["suggestions"] for m in s["moves"] if m["type"] != "cash")
    assert r["rules"]["max_asset_reuse"] == 2 and max(use.values()) <= 2


def test_ideas_on_top_of_a_chosen_trade(result, league):
    """After a trade is picked, the new ideas are legal in the state it leaves and their win
    change is measured from there."""
    from tradesim.checker import check_trades_in_sequence
    _, engine = result
    cba = load_cba()
    first = suggest("BOS", engine, league, cba, DATE)["suggestions"][0]
    _, after = check_trades_in_sequence(league, cba, [{"moves": first["moves"]}], DATE)
    r = suggest("BOS", engine, league, cba, DATE, chosen={"moves": first["moves"], "league": after})
    assert r["on_top_of_chosen"] and r["suggestions"]
    for s in r["suggestions"]:
        both, _ = check_trades_in_sequence(league, cba, [{"moves": first["moves"]}, {"moves": s["moves"]}], DATE)
        assert all(x["works"] for x in both)
        assert abs(s["wins_before"] - (first["wins_after"])) < 0.05


def test_suggestions_endpoint_and_cache(tmp_path, monkeypatch):
    import server
    import tradesim.engine as eng
    import tradesim.suggest as sg
    monkeypatch.setattr(eng, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(sg, "BUNDLED_DIR", str(tmp_path / "bundled"))  # no shipped ideas: first call searches
    client = server.app.test_client()
    assert client.get("/api/sim/team/XYZ/suggestions").status_code == 404
    first = client.get("/api/sim/team/BKN/suggestions").get_json()
    second = client.get("/api/sim/team/BKN/suggestions").get_json()
    assert first["from_cache"] is False and second["from_cache"] is True
    assert first["suggestions"] == second["suggestions"]
    r = client.get("/api/sim/players/resolve?q=williams").get_json()
    assert r["status"] == "ambiguous" and all("name" in p for p in r["players"])


def test_lone_last_names(index):
    assert ai.names_ok("White's playmaking is the fit here.", [player_id("derrick-white"), player_id("walker-kessler")], index)
    assert not ai.names_ok("Williams would also help.", [player_id("derrick-white")], index)  # which Williams?


def test_shipped_ideas_are_used_when_an_llm_is_configured(tmp_path, monkeypatch, league):
    """With GROQ_API_KEY set (Vercel), the shipped no-LLM ideas still serve the starting ideas:
    no live search and no LLM call."""
    import json
    import tradesim.engine as eng
    import tradesim.suggest as sg

    class Boom:  # any use of the LLM fails the test
        def __getattr__(self, name):
            raise AssertionError("LLM was called")

    engine = Engine(league, load_schedule_2026_27(), load_sim_config(), n_sims=1000)
    cba = load_cba()
    monkeypatch.setattr(eng, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(sg, "BUNDLED_DIR", str(tmp_path / "bundled"))
    shipped = sg.suggest("BKN", engine, league, cba, DATE)
    path = sg.cache_path("BKN", engine, "no-llm", None, sg.BUNDLED_DIR) + f".{DATE.isoformat()}.json"
    (tmp_path / "bundled").mkdir()
    with open(path, "w") as f:
        json.dump(shipped, f)
    got = sg.cached_suggest("BKN", engine, league, cba, DATE, llm=Boom())
    assert got["from_cache"] is True
    assert got["suggestions"] == shipped["suggestions"]
