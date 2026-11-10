"""Scenario engine tests (sim-accuracy Stage 3): rotations, absences, scenarios."""
import numpy as np
import pytest

from tradesim.engine import Engine, draw_absences
from tradesim.games import load_schedule_2026_27
from tradesim.league import player_id, League
from tradesim.model import load_sim_config
from tradesim.ratings import load_ratings
from tradesim.rotation import Rotation, apply_moves, distance


@pytest.fixture(scope="module")
def cfg():
    return load_sim_config()


@pytest.fixture(scope="module")
def league():
    return League.load()


@pytest.fixture(scope="module")
def engine(league, cfg):
    return Engine(league, load_schedule_2026_27(), cfg, n_sims=2000)


def move(pid, frm, to):
    return {"player": pid, "from": frm, "to": to}


# --- spec tests ---------------------------------------------------------------------------------

def test_moving_a_player_to_his_own_team_changes_nothing(engine):
    out = engine.scenario([move(player_id("nikola-jokic"), "DEN", "DEN")])
    assert out["changed_teams"] == []
    assert all(t["win_change"] == 0 and t["playoff_change"] == 0 for t in out["teams"].values())


def test_swapping_near_equal_players_barely_moves_wins(engine):
    # Derrick White (BOS) and Dyson Daniels (ATL): guards, impact +2.3, 31 minutes, 86% of games.
    out = engine.scenario([move(player_id("derrick-white"), "BOS", "ATL"), move(player_id("dyson-daniels"), "ATL", "BOS")])
    assert set(out["changed_teams"]) == {"ATL", "BOS"}
    assert abs(out["teams"]["BOS"]["win_change"]) < 0.5
    assert abs(out["teams"]["ATL"]["win_change"]) < 0.5


def test_same_seed_gives_identical_output(league, cfg):
    a = Engine(league, load_schedule_2026_27(), cfg, n_sims=500).scenario([move(player_id("kawhi-leonard"), "TOR", "CLE")])
    b = Engine(league, load_schedule_2026_27(), cfg, n_sims=500).scenario([move(player_id("kawhi-leonard"), "TOR", "CLE")])
    assert a["teams"] == b["teams"]


def test_minutes_always_sum_to_240(league, cfg):
    ratings = load_ratings()
    rotations = apply_moves(league, [move(player_id("kawhi-leonard"), "TOR", "CLE"), move(player_id("nikola-jokic"), "DEN", "CLE"),
                                     move(player_id("tyrese-maxey"), "PHI", "ATL")], cfg, ratings)
    for code, r in rotations.items():
        assert sum(r.minutes.values()) == pytest.approx(240), code
        # ... and in every game a player misses, after his minutes are handed out.
        for pid, m in r.minutes.items():
            if m > 0:
                after = r._give({k: v for k, v in r.minutes.items() if k != pid}, m,
                                r.players[pid]["position"], exclude={pid}, below=m)
                assert sum(after.values()) == pytest.approx(240), (code, pid)


# --- rotation rules ------------------------------------------------------------------------------

def test_positions_and_distance():
    assert distance("G", "G") == 0 and distance("G", "F") == 1 and distance("G", "C") == 2
    assert distance("F-C", "C") == 0 and distance("G-F", "C") == 1


def test_absent_players_minutes_go_to_same_position_backup_first(league, cfg):
    r = Rotation("DEN", league.roster("DEN"), cfg)
    jokic = r.players[player_id("nikola-jokic")]
    after = r._give({k: v for k, v in r.minutes.items() if k != player_id("nikola-jokic")}, r.minutes[player_id("nikola-jokic")],
                    jokic["position"], exclude={player_id("nikola-jokic")}, below=r.minutes[player_id("nikola-jokic")])
    gains = {k: after[k] - r.minutes[k] for k in after if after[k] > r.minutes[k] + 1e-9}
    first = max(gains, key=gains.get)
    assert distance(r.players[first]["position"], "C") == 0  # a center gets the most of Jokic's minutes
    assert all(after[k] <= r._ceiling(k) + 1e-9 for k in gains)


def test_incoming_player_fills_departing_players_minutes_first(league, cfg):
    rotations = apply_moves(league, [move(player_id("tyrese-maxey"), "PHI", "ATL"), move(player_id("jalen-johnson"), "ATL", "PHI")], cfg)
    phi = rotations["PHI"]
    base = Rotation("PHI", league.roster("PHI"), cfg)
    assert phi.minutes[player_id("jalen-johnson")] == pytest.approx(phi.players[player_id("jalen-johnson")]["usual"])
    # Existing players don't balloon: nobody gains more than 10 minutes.
    assert all(phi.minutes[k] <= base.minutes[k] + 10 + 1e-9 for k in base.minutes if k in phi.minutes)


def test_losing_a_star_for_nothing_hurts(league, cfg):
    base = Rotation("DEN", league.roster("DEN"), cfg)
    without = apply_moves(league, [move(player_id("nikola-jokic"), "DEN", "BKN")], cfg)["DEN"]
    assert without.full_strength() < base.full_strength() - 3
    assert without.expected_strength() < base.expected_strength() - 2


def test_absences_never_make_a_team_better_on_average(league, cfg):
    for code in league.teams:
        r = Rotation(code, league.roster(code), cfg)
        assert r.expected_strength() <= r.full_strength() + 1e-9, code


def test_diminishing_returns_only_for_stacked_teams(league, cfg):
    rotations = apply_moves(league, [move(player_id("shai-gilgeous-alexander"), "OKC", "DEN"),
                                     move(player_id("luka-doncic"), "LAL", "DEN")], cfg)
    stacked = rotations["DEN"]
    assert stacked.diminishing_returns() > 0.5
    assert Rotation("BKN", league.roster("BKN"), cfg).diminishing_returns() == 0
    # Mild: the haircut is a small share of what the stars add.
    stars = sum(stacked.players[k]["impact"] * stacked.minutes[k] / 48
                for k in (player_id("nikola-jokic"), player_id("shai-gilgeous-alexander"), player_id("luka-doncic")))
    assert stacked.diminishing_returns() < 0.25 * stars


# --- absences and the engine -----------------------------------------------------------------------

def test_absences_match_expected_availability_and_follow_the_player():
    ratings = load_ratings()
    draws = draw_absences([player_id("nikola-jokic"), player_id("tyrese-haliburton")], ratings, 2.1, 20000, seed=1)
    for pid, (missed, start) in draws.items():
        played = 1 - missed.mean() / 82
        assert played == pytest.approx(ratings["players"][pid]["availability"], abs=0.02)
        assert (start + missed <= 82).all()
    again = draw_absences([player_id("tyrese-haliburton")], ratings, 2.1, 20000, seed=1)
    assert np.array_equal(again[player_id("tyrese-haliburton")][0], draws[player_id("tyrese-haliburton")][0])


def test_unchanged_teams_keep_identical_strength(engine):
    out = engine.scenario([move(player_id("kawhi-leonard"), "TOR", "CLE")])
    for code, t in out["teams"].items():
        if code not in ("TOR", "CLE"):
            assert t["strength_before"] == t["strength_after"]
    assert out["teams"]["CLE"]["win_change"] > 2 and out["teams"]["TOR"]["win_change"] < -2


def test_engine_totals(engine):
    base = engine.baseline()
    assert (base["wins"].sum(axis=1) == 1230).all()
    assert engine.residual_sd > 0


# --- Stage 6: runs, cache, paired changes ------------------------------------------------------------

def test_config_runs_10000_seasons(cfg):
    assert cfg["simulation"]["n_seasons"] == 10000


def test_baseline_cache_returns_identical_results(league, cfg, tmp_path, monkeypatch):
    import tradesim.engine as eng
    monkeypatch.setattr(eng, "CACHE_DIR", str(tmp_path))
    first = Engine(league, load_schedule_2026_27(), cfg, n_sims=600).baseline()
    second = Engine(league, load_schedule_2026_27(), cfg, n_sims=600).baseline()
    assert not first["from_cache"] and second["from_cache"]
    assert np.array_equal(first["wins"], second["wins"]) and first["teams"] == second["teams"]
    # A different number of seasons is a different cache entry.
    assert not Engine(league, load_schedule_2026_27(), cfg, n_sims=500).baseline()["from_cache"]


def test_chunked_runs_are_reproducible_and_chunk_size_only_reshuffles_noise(league, cfg):
    chunked = {**cfg, "simulation": {**cfg["simulation"], "chunk_size": 250}}
    a = Engine(league, load_schedule_2026_27(), chunked, n_sims=500).baseline(use_cache=False)
    b = Engine(league, load_schedule_2026_27(), chunked, n_sims=500).baseline(use_cache=False)
    assert np.array_equal(a["wins"], b["wins"])
    # Chunk size changes which noise each season gets, but not the model: averages agree.
    other = {**cfg, "simulation": {**cfg["simulation"], "chunk_size": 500}}
    c = Engine(league, load_schedule_2026_27(), other, n_sims=500).baseline(use_cache=False)
    assert abs(a["teams"]["OKC"]["mean_wins"] - c["teams"]["OKC"]["mean_wins"]) < 1.5


def test_paired_changes_have_small_mcse(engine):
    out = engine.scenario([move(player_id("kawhi-leonard"), "TOR", "CLE")])
    cle = out["teams"]["CLE"]
    paired = cle["delta"]["mean_wins"]["mcse"]
    unpaired = np.hypot(cle["before"]["mcse"]["mean_wins"], cle["after"]["mcse"]["mean_wins"])
    assert paired < unpaired / 2           # sharing random draws makes changes far more precise
    assert cle["changed_roster"] and cle["moved"]
    assert cle["delta"]["mean_wins"]["change"] > 10 * paired


def test_only_meaningful_ripples_are_highlighted(engine):
    out = engine.scenario([move(player_id("derrick-white"), "BOS", "ATL"), move(player_id("dyson-daniels"), "ATL", "BOS")])
    flagged = {c for c, t in out["teams"].items() if t["moved"]}
    assert flagged == {"ATL", "BOS"}  # roster changes only; near-equal swap moves nobody else


def test_scenario_report_files(engine, tmp_path):
    from tradesim.report import scenario_markdown, write_scenario_reports
    out = engine.scenario([move(player_id("kawhi-leonard"), "TOR", "CLE")])
    csv_path, md_path = write_scenario_reports(out, "test", "Test", directory=str(tmp_path))
    text = open(md_path).read()
    assert text.isascii() and "| ** | CLE |" in text and "| ** | TOR |" in text
    rows = [line for line in text.splitlines() if line.startswith("| ") and "Team" not in line]
    assert len(rows) == 30 and all(line.count("|") == 13 for line in rows)
    assert "Win range (10-90%)" in text and "80% range" in text
    assert open(csv_path).read().count("\n") == 31


def test_trade_delta_has_80_percent_interval(engine):
    d = engine.scenario([move(player_id("kawhi-leonard"), "TOR", "CLE")])["teams"]["CLE"]["delta"]["mean_wins"]
    assert d["p10"] <= d["change"] <= d["p90"]
    assert d["p90"] - d["p10"] > 10 * d["mcse"]  # spread of outcomes is much wider than the MC SE


def test_league_wins_total_1230_in_scenarios_too(engine):
    rotations = __import__("tradesim.rotation", fromlist=["apply_moves"]).apply_moves(
        engine.league, [move(player_id("kawhi-leonard"), "TOR", "CLE"), move(player_id("nikola-jokic"), "DEN", "BKN")], engine.cfg,
        engine.ratings)
    sim = engine.simulate(rotations, ["TOR", "CLE", "DEN", "BKN"])
    assert (sim["wins"].sum(axis=1) == 1230).all()
