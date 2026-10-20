from contracts import CONTRACT_DATA_NOTE, get_league_cap_info, get_player_contract, latest_cap_season


def test_get_player_contract_returns_rows_for_a_covered_player():
    rows = get_player_contract("Jalen Brunson")
    assert rows is not None
    assert {r["season"] for r in rows} == {"2026-27", "2027-28"}
    assert all(r["team"] == "Knicks" for r in rows)
    assert all(isinstance(r["salary"], int) and r["salary"] > 0 for r in rows)


def test_get_player_contract_is_case_and_accent_insensitive():
    assert get_player_contract("jalen brunson") is not None
    assert get_player_contract("JALEN BRUNSON") is not None


def test_get_player_contract_returns_none_for_a_player_this_partial_extract_missed():
    # This dataset only covers ~95 of the league's ~450 players.
    assert get_player_contract("Not A Real Player") is None


def test_get_player_contract_excludes_rows_with_no_real_salary():
    # Portland has a row in the raw extract but its salary is null.
    assert get_player_contract("Deni Avdija") is None


def test_latest_cap_season_and_league_cap_info():
    season = latest_cap_season()
    info = get_league_cap_info()
    assert info == get_league_cap_info(season)
    assert info["salary_cap"] < info["luxury_tax_line"] < info["first_apron"] < info["second_apron"]


def test_get_league_cap_info_falls_back_for_unknown_season():
    assert get_league_cap_info("1999-00") == get_league_cap_info()


def test_contract_data_note_flags_dataset_as_partial_and_unverified():
    lowered = CONTRACT_DATA_NOTE.lower()
    assert "partial" in lowered and "unverified" in lowered
