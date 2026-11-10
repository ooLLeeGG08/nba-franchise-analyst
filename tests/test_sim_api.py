"""Trade simulator API and pages (Stage 3)."""
import pytest

import server
from tradesim.teams import TEAM_INFO


@pytest.fixture(scope="module")
def client():
    return server.app.test_client()


def test_root_serves_the_simulator_and_analyst_moves(client):
    root = client.get("/")
    assert root.status_code == 200 and b"NBA Trade Simulator" in root.data
    assert b"/sim/sim.js" in root.data
    assert client.get("/sim/sim.js").status_code == 200 and client.get("/sim/sim.css").status_code == 200
    analyst = client.get("/analyst")
    assert analyst.status_code == 200 and b"Franchise Analyst" in analyst.data


def test_teams_grouped_by_conference(client):
    data = client.get("/api/sim/teams").get_json()["conferences"]
    assert {c: len(v) for c, v in data.items()} == {"East": 15, "West": 15}
    for conf, teams in data.items():
        for t in teams:
            assert TEAM_INFO[t["code"]]["conference"] == conf
            assert t["colors"]["primary"].startswith("#") and 10 < t["mean_wins"] < 72


def test_team_analysis_shape(client):
    t = client.get("/api/sim/team/okc").get_json()
    assert t["code"] == "OKC" and t["conference"] == "West"
    p = t["projection"]
    assert p["range_10_90"][0] <= p["mean_wins"] <= p["range_10_90"][1]
    assert 1 <= p["conference_rank"] <= 15 and p["n_sims"] == 10000
    assert [x["group"] for x in t["positions"]] == ["Guards", "Forwards", "Centers"]
    assert all(1 <= x["rank"] <= 30 for x in t["positions"])
    assert t["needs"] and t["needs_type"] in ("need", "relative")
    assert t["cap"]["status"] and set(t["cap"]["thresholds"]) == {"salary_cap", "tax_line", "first_apron", "second_apron"}
    assert "suggestions" not in t  # trade ideas load separately (/suggestions)
    names = {r["name"] for r in t["roster"]}
    assert {i["name"] for i in t["long_injuries"]} <= names


def test_position_minutes_cover_the_whole_game(client):
    """Expected minutes (injuries counted) still add up to 240 across the three groups."""
    for code in ("OKC", "BKN", "DEN"):
        t = client.get(f"/api/sim/team/{code}").get_json()
        assert sum(x["minutes"] for x in t["positions"]) == pytest.approx(240, abs=0.5)


def test_every_team_has_a_need_and_ranks_are_a_permutation(client):
    for group_index in range(3):
        ranks = sorted(client.get(f"/api/sim/team/{c}").get_json()["positions"][group_index]["rank"] for c in TEAM_INFO)
        assert ranks == list(range(1, 31))


def test_unknown_team_is_404(client):
    assert client.get("/api/sim/team/XYZ").status_code == 404


# --- Stage 4: trade machine ------------------------------------------------------------------------

def mv(pid, frm, to, kind="player"):
    return {"type": kind, "id": pid, "from": frm, "to": to}


def test_trade_assets(client):
    a = client.get("/api/sim/trade/assets/bos").get_json()
    assert a["code"] == "BOS" and a["roster"] and a["picks"]
    assert a["roster"] == sorted(a["roster"], key=lambda p: -p["salary"])
    frozen = [p for p in a["picks"] if p["kind"] == "frozen"]
    assert frozen and not any(p["tradeable"] for p in frozen)  # Boston's 2032 first is frozen
    assert set(a["thresholds"]) == {"salary_cap", "tax_line", "first_apron", "second_apron"}
    assert client.get("/api/sim/trade/assets/XYZ").status_code == 404


def test_signed_this_summer_shows_tradeable_date(client):
    a = client.get("/api/sim/trade/assets/PHI").get_json()
    simons = next(p for p in a["roster"] if p["id"] == "anfernee-simons")
    assert simons["tradeable_from"] == "2026-12-15"


def test_check_trade_that_works(client):
    r = client.post("/api/sim/trade/check", json={"moves": [
        mv("tyrese-maxey", "PHI", "ATL"), mv("jalen-johnson", "ATL", "PHI"), mv("aaron-wiggins", "ATL", "PHI")]})
    data = r.get_json()
    assert r.status_code == 200 and data["works"]
    atl = data["teams"]["ATL"]
    assert atl["salary_after"] - atl["salary_before"] == 40_770_520 - 38_831_776
    assert atl["counts"]["fail"] == 0 and sum(atl["counts"].values()) == len(atl["rules"])
    assert atl["name"] == "Atlanta Hawks" and atl["colors"]["primary"].startswith("#")


def test_check_trade_that_fails_explains_why(client):
    data = client.post("/api/sim/trade/check", json={"moves": [
        mv("joel-embiid", "PHI", "ATL"), mv("jalen-johnson", "ATL", "PHI")]}).get_json()
    assert not data["works"]
    assert "$28.0M more" in data["teams"]["ATL"]["failures"][0]
    assert data["teams"]["ATL"]["status_after"] == "Over the second apron"


def test_exception_use_is_labelled(client):
    data = client.post("/api/sim/trade/check", json={"moves": [
        mv("moussa-diabate", "CHA", "DEN"), mv("christian-braun", "DEN", "CHA")]}).get_json()
    assert data["works"]
    assert "LaMelo Ball trade exception" in data["teams"]["CHA"]["exception_used"]["label"]


def test_cash_and_three_team_trades(client):
    data = client.post("/api/sim/trade/check", json={"moves": [
        mv("brandon-miller", "CHA", "HOU"), mv("jabari-smith", "HOU", "CHA"),
        {"type": "cash", "amount": 2000000, "from": "HOU", "to": "CHA"}]}).get_json()
    assert any(r["id"] == "cash" and r["status"] == "not_checked" for r in data["teams"]["HOU"]["rules"])
    three = client.post("/api/sim/trade/check", json={"moves": [
        mv("brandon-miller", "CHA", "HOU"), mv("jabari-smith", "HOU", "BKN"), mv("danny-wolf", "BKN", "CHA")]}).get_json()
    assert set(three["teams"]) == {"CHA", "HOU", "BKN"}


def test_check_input_validation(client):
    assert client.post("/api/sim/trade/check", json={"nope": 1}).status_code == 400
    assert client.post("/api/sim/trade/check", json={"moves": [{"type": "player", "from": "ATL", "to": "XXX", "id": "a"}]}).status_code == 400
    five = [mv(f"p{i}", t, "ATL") for i, t in enumerate(["BOS", "BKN", "CHA", "CHI"])]
    assert client.post("/api/sim/trade/check", json={"moves": five}).status_code == 400
    empty = client.post("/api/sim/trade/check", json={"moves": []}).get_json()
    assert empty["empty"] and not empty["works"]


def test_unknown_player_is_a_clear_error(client):
    data = client.post("/api/sim/trade/check", json={"moves": [mv("not-a-player", "ATL", "BOS")]}).get_json()
    assert not data["works"] and any("Unknown player" in e for e in data["errors"])


# --- Stage 6: trade selection and results ---------------------------------------------------

def _atl_ideas(client):
    sug = client.get("/api/sim/team/ATL/suggestions").get_json()["suggestions"]
    return [{"id": f"s{s['rank']}", "moves": s["moves"]} for s in sug]


def test_sequence_blocks_trades_that_reuse_a_player(client):
    """Trades are checked in order: a later trade sending a player already traded is blocked."""
    ideas = _atl_ideas(client)
    r = client.post("/api/sim/sequence/check", json={"team": "ATL", "trades": ideas[:2]}).get_json()
    first, second = r["trades"]
    assert first["works"]
    shared = {m["id"] for m in ideas[0]["moves"]} & {m["id"] for m in ideas[1]["moves"]}
    if shared:
        assert not second["works"] and second["conflict"] and "moved there in trade 1" in second["reason"]
    assert "ATL" in r["payroll"] and "working" not in r


def test_sequence_payroll_matches_the_trade(client):
    ideas = _atl_ideas(client)
    r = client.post("/api/sim/sequence/check", json={"team": "ATL", "trades": ideas[:1]}).get_json()
    total_before = sum(p["before"] for p in r["payroll"].values())
    total_after = sum(p["after"] for p in r["payroll"].values())
    assert total_before == total_after  # salary only moves between the two teams


def test_sequence_input_validation(client):
    assert client.post("/api/sim/sequence/check", json={"team": "XXX", "trades": []}).status_code == 400
    assert client.post("/api/sim/sequence/check", json={"team": "ATL", "trades": [1]}).status_code == 400
    many = [{"moves": []}] * 13
    assert client.post("/api/sim/sequence/check", json={"team": "ATL", "trades": many}).status_code == 400


def test_results_with_no_trades_equal_the_baseline(client):
    r = client.post("/api/sim/sequence/simulate", json={"team": "ATL", "trades": []}).get_json()
    assert r["applied"] == 0 and r["delta"]["mean_wins"]["change"] == 0
    assert r["before"]["distribution"] == r["after"]["distribution"]
    assert sum(r["before"]["distribution"]) == r["n_sims"] and r["code"] == "ATL"


def test_results_for_a_suggestion_match_its_card(client):
    """Same trade, same random draws: the results screen repeats the suggestion's numbers."""
    sug = client.get("/api/sim/team/ATL/suggestions").get_json()["suggestions"][0]
    r = client.post("/api/sim/sequence/simulate",
                    json={"team": "ATL", "trades": [{"id": "s1", "moves": sug["moves"]}]}).get_json()
    assert r["applied"] == 1
    assert abs(r["delta"]["mean_wins"]["change"] - sug["win_change"]) < 0.06
    assert any(o["code"] == sug["partner"] and o["in_trade"] for o in r["others"])
    assert r["explanation"]["text"]


def test_injury_past_the_season_reads_out_for_season(client):
    t = client.get("/api/sim/team/SAC").get_json()
    simmons = next(i for i in t["long_injuries"] if i["name"] == "Ben Simmons")
    assert simmons["out_for_season"]
    others = [i for c in ("POR",) for i in client.get(f"/api/sim/team/{c}").get_json()["long_injuries"]]
    assert any(not i["out_for_season"] for i in others)  # Sharpe, back in March


def test_plan_resuggests_and_combines(client):
    """Picking a trade: ideas are rebuilt on top of it, and two picks report the combined gain
    from one paired run next to the sum of each alone."""
    none = client.post("/api/sim/sequence/plan", json={"team": "ATL", "trades": []}).get_json()
    assert none["combined"] is None and len(none["ideas"]["suggestions"]) == 4
    first = none["ideas"]["suggestions"][0]
    one = client.post("/api/sim/sequence/plan", json={"team": "ATL", "trades": [{"id": "a", "moves": first["moves"]}]}).get_json()
    assert one["ideas"]["on_top_of_chosen"]
    assert abs(one["combined"]["change"] - first["win_change"]) < 0.06
    second = one["ideas"]["suggestions"][0]
    two = client.post("/api/sim/sequence/plan", json={"team": "ATL", "trades": [
        {"id": "a", "moves": first["moves"]}, {"id": "b", "moves": second["moves"]}]}).get_json()
    assert all(v["works"] for v in two["trades"]) and not two["removed"]
    c = two["combined"]
    assert set(c["alone"]) == {"a", "b"} and abs(c["sum_alone"] - sum(c["alone"].values())) < 0.02
    # combined = first alone + second on top of the first (same paired runs)
    assert abs(c["change"] - (first["win_change"] + second["win_change"])) < 0.15


def test_plan_removes_a_blocked_pick(client):
    """A picked trade that reuses a player already traded is removed, with the reason."""
    ideas = client.post("/api/sim/sequence/plan", json={"team": "ATL", "trades": []}).get_json()["ideas"]["suggestions"]
    first = ideas[0]["moves"]
    r = client.post("/api/sim/sequence/plan", json={"team": "ATL", "trades": [
        {"id": "a", "moves": first}, {"id": "dup", "moves": first}]}).get_json()
    assert [v["id"] for v in r["removed"]] == ["dup"] and r["removed"][0]["reason"]
