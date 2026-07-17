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
