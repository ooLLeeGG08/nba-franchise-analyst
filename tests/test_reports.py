"""Report output tests: every row complete, numbers numeric, one consistent sort, paste-safe text."""
import csv

import pytest

from tradesim.report import COLUMNS, markdown, ranked_rows, terminal_summary, write_reports
from tradesim.simulate import season_table


@pytest.fixture(scope="module")
def table():
    return season_table()


@pytest.fixture(scope="module")
def written(table, tmp_path_factory):
    directory = tmp_path_factory.mktemp("reports")
    return write_reports(table, "test", "Test", notes=["note"], directory=str(directory))


def test_raw_rows_are_complete_and_numeric(table):
    assert len(table) == 30
    for r in table:
        assert set(r) == {"team", "conference", "strength", "mean_wins", "range", "playoff_pct", "play_in_pct",
                          "top_seed_pct", "mcse", "injury_adjusted"}
        for key in ("strength", "mean_wins", "playoff_pct", "play_in_pct", "top_seed_pct"):
            assert isinstance(r[key], (int, float)), (r["team"], key)
        assert r["range"][0] <= r["mean_wins"] <= r["range"][1]


def test_rows_sorted_by_wins_within_each_conference(table):
    rows = ranked_rows(table)
    for conference in ("East", "West"):
        conf = [r for r in rows if r["conference"] == conference]
        assert [r["rank"] for r in conf] == list(range(1, 16))
        assert [r["mean_wins"] for r in conf] == sorted((r["mean_wins"] for r in conf), reverse=True)


def test_csv_has_every_column_and_same_numbers(table, written):
    with open(written[0]) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 30
    assert list(rows[0]) == COLUMNS
    assert all(all(v != "" for v in r.values()) for r in rows)
    by_team = {r["team"]: r for r in table}
    for r in rows:
        assert float(r["strength"]) == by_team[r["team"]]["strength"]
        assert float(r["mean_wins"]) == by_team[r["team"]]["mean_wins"]


def test_markdown_rows_all_have_eight_cells_and_are_ascii(written):
    text = open(written[1]).read()
    assert text.isascii()
    table_lines = [line for line in text.splitlines() if line.startswith("|")]
    assert len(table_lines) == 2 * (15 + 2)  # header + divider + 15 teams, per conference
    assert all(line.count("|") == 10 for line in table_lines)


def test_strength_shows_as_signed_number_not_percent(written):
    rows = [line for line in open(written[1]).read().splitlines() if line.startswith("| ") and "Team" not in line]
    for line in rows:
        strength = line.split("|")[3].strip()
        assert strength[0] in "+-" and "%" not in strength
        float(strength)


def test_terminal_summary_is_narrow_and_ascii(table):
    text = terminal_summary(table)
    assert text.isascii()
    assert max(len(line) for line in text.splitlines()) <= 50


def test_markdown_does_not_change_numbers(table):
    rows = ranked_rows(table)
    md = markdown(rows, "x")
    sac = next(r for r in rows if r["team"] == "SAC")
    assert f"| SAC | {sac['strength']:+.1f} | {sac['mean_wins']:.1f} |" in md
