import rag
from rag import (
    resolve_team,
    mentioned_teams,
    resolve_season,
    get_team_roster,
    retrieve_context,
    latest_season,
    get_team_knowledge,
    get_team_advanced_stats,
    get_player_advanced_stats,
    get_team_recent_games,
    get_team_season_snapshot,
    get_team_branding,
    get_all_teams,
    get_league_leaders,
)


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


def test_retrieve_context_omits_trade_history_line_when_absent(monkeypatch):
    monkeypatch.delitem(rag.KNOWLEDGE["Spurs"], "trade_history", raising=False)
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


def test_latest_season_returns_newest_season_key():
    assert latest_season() == "2025-26"


def test_get_team_knowledge_returns_dict_for_known_team():
    info = get_team_knowledge("Spurs")
    assert info is not None
    assert info["full_name"] == "San Antonio Spurs"


def test_get_team_knowledge_returns_none_for_unknown_team():
    assert get_team_knowledge("NotATeam") is None


def test_get_team_advanced_stats_covers_all_seasons():
    stats = get_team_advanced_stats("Spurs")
    assert stats is not None
    assert "2025-26" in stats
    assert "off_rating" in stats["2025-26"]
    assert "def_rating_rank" in stats["2025-26"]


def test_get_player_advanced_stats_returns_list_for_known_team_season():
    players = get_player_advanced_stats("Spurs", "2025-26")
    assert players is not None
    assert any(p["player"] == "Victor Wembanyama" for p in players)


def test_get_player_advanced_stats_returns_none_for_unknown_season():
    assert get_player_advanced_stats("Spurs", "1998-99") is None


def test_get_team_recent_games_returns_current_season_games():
    games = get_team_recent_games("Spurs")
    assert games is not None
    assert len(games) > 0
    assert {"date", "opponent", "result", "pts_for", "pts_against"} <= games[0].keys()


def test_get_team_season_snapshot_computes_accurate_percentages(monkeypatch):
    monkeypatch.setitem(rag.RECENT_GAMES, "Spurs", [
        {"result": "W", "pts_for": 110, "pts_against": 100, "fgm": 40, "fga": 80, "fg3m": 10, "fg3a": 20, "ftm": 20, "fta": 25, "reb": 45, "ast": 25, "tov": 12},
        {"result": "L", "pts_for": 90, "pts_against": 100, "fgm": 30, "fga": 80, "fg3m": 5, "fg3a": 20, "ftm": 25, "fta": 25, "reb": 35, "ast": 15, "tov": 18},
    ])
    snapshot = get_team_season_snapshot("Spurs")
    assert snapshot["wins"] == 1
    assert snapshot["losses"] == 1
    assert snapshot["win_pct"] == 0.5
    assert snapshot["ppg"] == 100.0
    assert snapshot["opp_ppg"] == 100.0
    assert snapshot["point_diff"] == 0.0
    # FG% must be sum(makes)/sum(attempts), not an average of per-game percentages
    assert snapshot["fg_pct"] == round(70 / 160, 3)
    assert snapshot["ft_pct"] == round(45 / 50, 3)


def test_get_team_season_snapshot_returns_none_for_unknown_team():
    assert get_team_season_snapshot("NotATeam") is None


def test_get_team_branding_returns_colors_and_abbreviation():
    branding = get_team_branding("Lakers")
    assert branding["abbreviation"] == "LAL"
    assert branding["primary"].startswith("#")


def test_get_all_teams_returns_all_30_teams_with_expected_shape():
    teams = get_all_teams()
    assert len(teams) == 30
    spurs = next(t for t in teams if t["key"] == "Spurs")
    assert spurs["full_name"] == "San Antonio Spurs"
    assert spurs["colors"]["primary"] == "#C4CED4"


def test_get_league_leaders_ppg_is_sorted_descending():
    leaders = get_league_leaders("ppg")
    values = [entry["value"] for entry in leaders]
    assert values == sorted(values, reverse=True)
    assert all("team" in entry for entry in leaders)


def test_get_league_leaders_unknown_category_returns_empty_list():
    assert get_league_leaders("blocks") == []


def test_get_league_leaders_pie_excludes_low_sample_players(monkeypatch):
    monkeypatch.setitem(rag.PLAYER_ADVANCED, "Spurs", {
        "2025-26": [
            {"player": "Small Sample Guy", "gp": 1, "min": 6.8, "pie": 0.9},
            {"player": "Real Starter", "gp": 65, "min": 30.0, "pie": 0.5},
        ]
    })
    leaders = get_league_leaders("pie")
    names = [entry["player"] for entry in leaders]
    assert "Real Starter" in names
    assert "Small Sample Guy" not in names
