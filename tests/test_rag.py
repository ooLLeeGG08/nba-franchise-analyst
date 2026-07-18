import rag
from rag import resolve_team, mentioned_teams, resolve_season, get_team_roster, retrieve_context


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


def test_resolve_season_from_current_message_season_key_format():
    assert resolve_season("Tell me about the 2015-16 Nets", []) == "2015-16"


def test_resolve_season_from_current_message_verbose_format():
    assert resolve_season("Tell me about the 2015-2016 Nets", []) == "2015-16"


def test_resolve_season_from_current_message_bare_year():
    assert resolve_season("Tell me about the Nets in 2018", []) == "2018-19"


def test_resolve_season_falls_back_to_history():
    history = [
        {"role": "user", "content": "Tell me about the Nets in 2015-16"},
        {"role": "assistant", "content": "That roster included Brook Lopez."},
    ]
    assert resolve_season("Who else was on that roster?", history) == "2015-16"


def test_resolve_season_defaults_to_latest_when_nothing_found():
    assert resolve_season("Tell me about the Nets", []) == "2025-26"


def test_resolve_season_ignores_out_of_range_year():
    assert resolve_season("Tell me about the Nets in 1998", []) == "2025-26"


def test_get_team_roster_returns_list_for_known_team_season():
    roster = get_team_roster("Nets", "2015-16")
    assert roster is not None
    assert any(p["player"] == "Shane Larkin" for p in roster)


def test_get_team_roster_returns_none_for_unknown_season():
    assert get_team_roster("Nets", "1998-99") is None


def test_retrieve_context_includes_roster_line_for_resolved_season():
    doc = retrieve_context("Nets", "2015-16")
    assert "Roster (2015-16):" in doc
    assert "Shane Larkin (G)" in doc


def test_retrieve_context_omits_roster_line_when_season_has_no_data():
    doc = retrieve_context("Nets", "1998-99")
    assert "Roster (" not in doc


def test_retrieve_context_omits_trade_history_line_when_absent():
    doc = retrieve_context("Spurs", "2015-16")
    assert "Trade history:" not in doc


def test_retrieve_context_includes_trade_history_line_when_present(monkeypatch):
    monkeypatch.setitem(rag.KNOWLEDGE["Spurs"], "trade_history", [
        {
            "season": "2018-19",
            "trade": "Traded Kawhi Leonard and Danny Green to Toronto for DeMar DeRozan, Jakob Poeltl, and a protected first-round pick",
            "outcome": "Reset the roster after Leonard's trade request rather than rebuilding from scratch.",
        }
    ])
    doc = retrieve_context("Spurs", "2015-16")
    assert (
        "Trade history: 2018-19 Traded Kawhi Leonard and Danny Green to Toronto for "
        "DeMar DeRozan, Jakob Poeltl, and a protected first-round pick -> Reset the roster "
        "after Leonard's trade request rather than rebuilding from scratch."
    ) in doc


def test_retrieve_context_returns_empty_string_for_unknown_team():
    assert retrieve_context("NotATeam", "2015-16") == ""
