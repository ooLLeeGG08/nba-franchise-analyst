from rag import resolve_team, mentioned_teams


def test_mentioned_teams_does_not_match_nets_inside_hornets():
    """Regression test: 'Hornets' should NOT match Nets (which contains 'nets' substring)."""
    teams = mentioned_teams("And the Hornets?")
    assert teams == ["Hornets"], f"Expected ['Hornets'], got {teams}"
    assert "Nets" not in teams, "Should not match 'Nets' when asking about 'Hornets'"


def test_mentioned_teams_matches_nets_correctly():
    """Verify that legitimate 'Nets' mentions still work."""
    teams = mentioned_teams("Tell me about the Nets")
    assert "Nets" in teams
    assert "Hornets" not in teams


def test_mentioned_teams_matches_multi_word_aliases():
    """Verify multi-word aliases still work correctly."""
    teams = mentioned_teams("What about the Los Angeles Clippers?")
    assert "Clippers" in teams
    teams = mentioned_teams("Tell me about San Antonio")
    assert "Spurs" in teams
    teams = mentioned_teams("The Golden State Warriors are great")
    assert "Warriors" in teams


def test_resolve_team_from_current_message():
    assert resolve_team("Tell me about the Spurs", []) == "Spurs"


def test_resolve_team_falls_back_to_history():
    history = [
        {"role": "user", "content": "Tell me about the Spurs"},
        {"role": "assistant", "content": "The Spurs have had great continuity."},
    ]
    assert resolve_team("What about their draft picks?", history) == "Spurs"


def test_resolve_team_prefers_current_message_over_history():
    history = [
        {"role": "user", "content": "Tell me about the Spurs"},
        {"role": "assistant", "content": "The Spurs have had great continuity."},
    ]
    assert resolve_team("What about the Celtics?", history) == "Celtics"


def test_resolve_team_ignores_assistant_turns_when_falling_back():
    history = [
        {"role": "user", "content": "What makes a great coach?"},
        {"role": "assistant", "content": "The Spurs' Gregg Popovich is a great example."},
    ]
    assert resolve_team("Tell me more", history) is None


def test_resolve_team_returns_none_when_nothing_found():
    assert resolve_team("What makes a great coach?", []) is None
