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
    assert t["suggestions"]["items"] == []
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
