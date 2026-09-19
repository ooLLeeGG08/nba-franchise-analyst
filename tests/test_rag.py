import rag
from rag import (
    resolve_team,
    mentioned_teams,
    resolve_season,
    get_team_roster,
    retrieve_context,
    latest_season,
    available_seasons,
    get_team_knowledge,
    get_team_advanced_stats,
    get_player_advanced_stats,
    get_team_recent_games,
    get_team_season_snapshot,
    get_team_branding,
    get_all_teams,
    get_league_leaders,
    resolve_player,
    mentioned_players,
    get_player_view,
    build_context,
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


def test_get_team_recent_games_defaults_to_latest_season():
    games = get_team_recent_games("Spurs")
    assert games is not None
    assert len(games) > 0
    assert {"date", "opponent", "result", "pts_for", "pts_against"} <= games[0].keys()


def test_get_team_recent_games_returns_requested_season():
    games_2015 = get_team_recent_games("Spurs", "2015-16")
    games_latest = get_team_recent_games("Spurs")
    assert games_2015 is not None
    assert games_2015 != games_latest


def test_get_team_recent_games_returns_none_for_unknown_season():
    assert get_team_recent_games("Spurs", "1998-99") is None


def test_get_team_season_snapshot_returns_requested_season():
    snapshot_2015 = get_team_season_snapshot("Spurs", "2015-16")
    snapshot_latest = get_team_season_snapshot("Spurs")
    assert snapshot_2015 is not None
    assert snapshot_2015 != snapshot_latest


def test_available_seasons_returns_all_eleven_seasons():
    assert available_seasons() == [
        "2015-16", "2016-17", "2017-18", "2018-19", "2019-20",
        "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26",
    ]


def test_resolve_player_matches_full_name():
    assert resolve_player("How is Victor Wembanyama doing") == "Victor Wembanyama"


def test_resolve_player_matches_unique_first_name():
    assert resolve_player("Analyze LeBron") == "LeBron James"


def test_resolve_player_returns_none_for_ambiguous_common_surname():
    # Multiple tracked players share the surname "Green" -- must not guess.
    assert resolve_player("Tell me about Green") is None


def test_resolve_player_returns_none_when_no_player_mentioned():
    assert resolve_player("Why do the Spurs win so much?") is None


def test_resolve_player_falls_back_to_history():
    history = [
        {"role": "user", "content": "Tell me about LeBron James"},
        {"role": "assistant", "content": "He's a Laker."},
    ]
    assert resolve_player("What's his position?", history) == "LeBron James"


def test_get_player_view_returns_team_position_and_history():
    view = get_player_view("LeBron James")
    assert view is not None
    assert view["team"] == "Lakers"
    assert view["position"] == "F"
    assert len(view["history"]) > 0
    assert view["history"][-1]["player"] == "LeBron James"


def test_get_player_view_returns_real_season_stats_for_any_rostered_player():
    # Regression: previously only players in their team's all-time top-5 (a
    # curated, name-mismatched dataset) got PPG/APG/RPG/SPG -- Jokic fell
    # through because the seed data spelled his name without the accent.
    view = get_player_view("Nikola Jokic")
    assert view["seasonStats"]["ppg"] > 20
    assert view["seasonStats"]["apg"] > 5
    assert view["seasonStats"]["rpg"] > 5


def test_get_player_view_returns_season_stats_for_lebron():
    view = get_player_view("LeBron James")
    assert "ppg" in view["seasonStats"]


def test_get_player_view_returns_none_for_unknown_player():
    assert get_player_view("Not A Real Player") is None


def test_mentioned_players_finds_multiple_players():
    players = mentioned_players("Compare LeBron James and Nikola Jokic")
    assert set(players) == {"LeBron James", "Nikola Jokić"}


def test_mentioned_players_matches_names_without_diacritics():
    assert mentioned_players("How good is Luka Doncic") == ["Luka Dončić"]


def test_get_player_view_matches_names_without_diacritics():
    assert get_player_view("Nikola Jokic") is not None


def test_build_context_includes_league_efficiency_leaders_even_with_no_team():
    context = build_context("Who is the most efficient scorer in the NBA right now?", [])
    assert "League-wide PIE" in context


def test_build_context_includes_team_advanced_stats_when_team_resolved():
    context = build_context("How efficient are the Spurs offensively?", [])
    assert "Advanced team stats" in context
    assert "Off rating" in context


def test_build_context_includes_single_player_stats():
    context = build_context("How is LeBron doing this season?", [])
    assert "LeBron James" in context
    assert "PIE" in context


def test_build_context_includes_both_players_in_comparison():
    context = build_context("Compare LeBron James and Nikola Jokic", [])
    assert "Player comparison:" in context
    assert "LeBron James" in context
    assert "Nikola Jokić" in context


def test_get_team_season_snapshot_computes_accurate_percentages(monkeypatch):
    monkeypatch.setitem(rag.RECENT_GAMES, "Spurs", {rag.latest_season(): [
        {"result": "W", "pts_for": 110, "pts_against": 100, "fgm": 40, "fga": 80, "fg3m": 10, "fg3a": 20, "ftm": 20, "fta": 25, "reb": 45, "ast": 25, "tov": 12},
        {"result": "L", "pts_for": 90, "pts_against": 100, "fgm": 30, "fga": 80, "fg3m": 5, "fg3a": 20, "ftm": 25, "fta": 25, "reb": 35, "ast": 15, "tov": 18},
    ]})
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


HYPOTHETICAL = "Would Maverick be a title contender after Luka-trade if AD and Kyrie didn't get injured?"


def test_mentioned_players_ignores_short_name_fragments_in_ordinary_words():
    """Regression: 'a' (Luc Mbah a Moute) matched the article in 'be a title contender'."""
    assert "Luc Mbah a Moute" not in mentioned_players(HYPOTHETICAL)
    assert mentioned_players("what a great house in the long run") == []


def test_mentioned_players_resolves_nicknames_and_ambiguous_first_names():
    assert mentioned_players(HYPOTHETICAL) == ["Luka Dončić", "Anthony Davis", "Kyrie Irving"]


def test_case_sensitive_initialisms_do_not_match_lowercase_words():
    assert mentioned_players("place an ad for the game") == []
    assert mentioned_players("AD or KD?") == ["Anthony Davis", "Kevin Durant"]


def test_full_name_is_not_also_matched_as_a_different_players_alias():
    assert mentioned_players("How is Luka Garza doing?") == ["Luka Garza"]


def test_common_word_surnames_need_capitalization():
    assert "Derrick Rose" in mentioned_players("Is Rose healthy?")
    assert mentioned_players("the rose bloomed") == []


def test_is_comparison_query():
    assert rag.is_comparison_query("LeBron vs Jokic")
    assert rag.is_comparison_query("Who is better, Tatum or Brown?")
    assert rag.is_comparison_query("Compare the Celtics and Nets")
    assert not rag.is_comparison_query(HYPOTHETICAL)
    assert not rag.is_comparison_query("Tell me about the Spurs")


def test_build_context_includes_every_mentioned_player_with_recent_seasons():
    context = build_context(HYPOTHETICAL, [])
    assert "Anthony Davis" in context and "Kyrie Irving" in context and "Luka Dončić" in context
    assert "2024-25 with Mavericks" in context  # AD's prior season, not just his latest
    assert "Player comparison:" not in context


def test_player_context_includes_per_game_stats_and_singular_team_name():
    context = build_context(HYPOTHETICAL, [])
    assert "PPG" in context and "APG" in context
    assert mentioned_teams(HYPOTHETICAL) == ["Mavericks"]
