from unittest.mock import patch

import server


def test_chat_endpoint_passes_history_to_answer_question():
    client = server.app.test_client()
    history = [{"role": "user", "content": "Tell me about the Spurs"}]

    with patch("server.answer_question", return_value="mocked answer") as mock_answer:
        response = client.post(
            "/api/chat",
            json={"message": "What about their draft picks?", "history": history},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["response"] == "mocked answer"
    assert data["team"] == "Spurs"
    mock_answer.assert_called_once_with("What about their draft picks?", history)


def test_chat_endpoint_defaults_history_to_empty_list():
    client = server.app.test_client()

    with patch("server.answer_question", return_value="mocked answer") as mock_answer:
        response = client.post("/api/chat", json={"message": "Tell me about the Celtics"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["team"] == "Celtics"
    mock_answer.assert_called_once_with("Tell me about the Celtics", [])


def test_chat_endpoint_returns_single_team_in_plural_teams_field():
    client = server.app.test_client()

    with patch("server.answer_question", return_value="mocked answer"):
        response = client.post("/api/chat", json={"message": "Tell me about the Celtics"})

    assert response.get_json()["teams"] == ["Celtics"]


def test_chat_endpoint_returns_both_teams_for_comparison_message():
    client = server.app.test_client()

    with patch("server.answer_question", return_value="mocked answer"):
        response = client.post("/api/chat", json={"message": "Compare the Lakers and Celtics"})

    data = response.get_json()
    assert set(data["teams"]) == {"Lakers", "Celtics"}
    assert data["team"] in data["teams"]


def test_chat_endpoint_returns_empty_teams_list_when_none_mentioned():
    client = server.app.test_client()

    with patch("server.answer_question", return_value="mocked answer"):
        response = client.post("/api/chat", json={"message": "What makes a great coach?"})

    assert response.get_json()["teams"] == []


def test_teams_list_endpoint_returns_all_30_teams():
    client = server.app.test_client()
    response = client.get("/api/teams")

    assert response.status_code == 200
    teams = response.get_json()
    assert len(teams) == 30
    assert {"key", "full_name", "abbreviation", "colors"} <= teams[0].keys()


def test_team_dashboard_endpoint_returns_full_bundle():
    client = server.app.test_client()
    response = client.get("/api/team/Spurs")

    assert response.status_code == 200
    data = response.get_json()
    assert data["team"] == "Spurs"
    for key in ("branding", "knowledge", "records", "advancedStats", "leaders", "recentGames", "roster", "season"):
        assert key in data


def test_team_dashboard_endpoint_is_case_insensitive():
    client = server.app.test_client()
    response = client.get("/api/team/spurs")

    assert response.status_code == 200
    assert response.get_json()["team"] == "Spurs"


def test_team_dashboard_endpoint_returns_404_for_unknown_team():
    client = server.app.test_client()
    response = client.get("/api/team/NotATeam")

    assert response.status_code == 404
    assert "error" in response.get_json()


def test_team_comparison_endpoint_returns_both_bundles():
    client = server.app.test_client()
    response = client.get("/api/team/Lakers/vs/Celtics")

    assert response.status_code == 200
    data = response.get_json()
    assert data["teamA"]["team"] == "Lakers"
    assert data["teamB"]["team"] == "Celtics"


def test_team_comparison_endpoint_returns_404_for_unknown_team():
    client = server.app.test_client()
    response = client.get("/api/team/Lakers/vs/NotATeam")

    assert response.status_code == 404


def test_leaders_endpoint_returns_all_categories():
    client = server.app.test_client()
    response = client.get("/api/leaders")

    assert response.status_code == 200
    data = response.get_json()
    assert set(data.keys()) == {"ppg", "apg", "rpg", "spg", "pie"}
    assert len(data["ppg"]) > 0
