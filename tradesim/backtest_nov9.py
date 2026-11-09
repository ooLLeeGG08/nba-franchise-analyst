"""Stage 7: backtest the full pipeline as of November 9, 2021-22 to 2025-26.

For each season, using only what was known on Nov 9 of that season:
  - Rating model (priors, rookie curve, uncertainty, residual persistence, availability)
    and game model are refitted with that season LEFT OUT.
  - Rosters and minutes: players who had played by Nov 9, on their team at the time
    (data/raw/backtest, from nba_api game logs). Minutes per game = minutes so far blended
    with last season's; availability from history plus games played so far.
  - Player impact = pre-season prior. (Basketball-Reference only has full-season tables, so
    early-season player BPM isn't available for past seasons; the live 2026-27 model also
    uses this season's BPM to date.)
  - Team residual: last season's, blended with results to Nov 9.
  - The full 82-game season is simulated from 0-0 on the real schedule, with tiebreakers
    and the play-in, once per value of sigma_t on a grid (all other draws identical).
Scored against what happened: win totals, the 16 playoff teams, top-6 and play-in.

sigma_t is chosen by the ranked probability score of each team's ACTUAL win total (a proper
score that uses the whole cumulative win distribution, so it rewards the right center and
spread), pooled over the five seasons; it is also chosen leave-one-season-out (pick on 4,
score the 5th). A first version used the log probability of the exact win total, which was
too noisy at 5,000 runs to separate nearby sigma_t values. Interval
coverage uses the mid-PIT (P(W < actual) + P(W = actual)/2), which handles whole-number
win totals.

Run:  python -m tradesim.backtest_nov9      (about a minute)
Writes data/model/backtest_nov9.json and reports/backtest_nov9.md.
"""
import json
import math
import os

import numpy as np

from tradesim import game_model as gm
from tradesim import ratings as rt
from tradesim.engine import Engine
from tradesim.games import actual_wins, schedule_from_results
from tradesim.history import load_season, previous
from tradesim.model import load_sim_config
from tradesim.names import name_key, slug
from tradesim.standings import official_standings
from tradesim.teams import TEAM_INFO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
SIGMA_GRID = [0.0, 0.5, 1.0, 1.5, 2.0, 2.33, 2.5, 3.0, 3.5]
N_SIMS = 5000
OUT_PATH = os.path.join(ROOT, "data", "model", "backtest_nov9.json")
VEGAS_PATH = os.path.join(ROOT, "data", "vegas_win_totals.csv")
BUCKETS = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0001)]


class PastLeague:
    """The minimum of tradesim.league.League the engine needs, for a past season."""

    def __init__(self, players):
        self.players = players
        self.teams = {code: TEAM_INFO[code] for code in TEAM_INFO}

    def roster(self, code):
        return [p for p in self.players.values() if p["team"] == code]


def _position(key, season):
    for s in (season, previous(season)):
        rec = load_season(s)[0].get(key)
        if rec and rec.get("pos"):
            return rec["pos"].replace("PG", "G").replace("SG", "G").replace("SF", "F").replace("PF", "F")
    return "F"


def build_season(season, fit, cfg):
    """(league, ratings) for `season` as of Nov 9, with the left-out fit."""
    with open(os.path.join(ROOT, "data", "raw", "backtest", f"asof_nov9_{season}.json")) as f:
        asof = json.load(f)
    rc = cfg["ratings"]
    c = fit["uncertainty"]["c"]
    players, rated = {}, {}
    for p in asof["players"]:
        if p["games"] == 0 or p["team"] not in TEAM_INFO:
            continue
        key = name_key(p["name"])
        pid = slug(p["name"])
        hist = rt.history(key, season, rc["history_seasons"])
        draft = rt.draft_picks().get(key)
        pick = draft[1] if draft and draft[0] <= int(season[:4]) else None
        totals = load_season(season)[0].get(key) or {}
        age = totals.get("age") or rt._target_age(hist)
        prior, tau = rt.prior_for(hist, age, pick, fit, cfg)
        mpg_before = rt.prior_mpg(key, pick, fit, cfg, season=season)
        team_games = asof["teams"][p["team"]]["games"]
        mpg_playing = (p["minutes"] + rc["minutes_prior_games"] * mpg_before) / (p["games"] + rc["minutes_prior_games"])
        avail = rt.availability(key, season, fit, cfg, games_now=p["games"], games_possible_now=team_games)
        players[pid] = {"id": pid, "name": p["name"], "team": p["team"], "position": _position(key, season),
                        "on_roster": True}
        rated[pid] = {"impact": prior, "se": tau, "mpg_when_playing": mpg_playing, "availability": avail,
                      "minutes_so_far": p["minutes"]}
    # Team residual: rho x (games-weighted last season's residual and this season's to Nov 9).
    rho = fit["team_residual"]["rho"]
    prev_resid = fit["team_residual"]["by_season"].get(previous(season), {})
    residuals = {}
    for code in TEAM_INFO:
        t = asof["teams"][code]
        observed = (t["points_for"] - t["points_against"]) / t["games"]
        player_sum = sum(rated[pid]["impact"] * rated[pid]["minutes_so_far"] / (t["games"] * 48)
                         for pid, p in players.items() if p["team"] == code)
        now = observed - player_sum
        g_prev = rt.season_games(previous(season))
        combined = (g_prev * prev_resid.get(code, 0.0) + t["games"] * now) / (g_prev + t["games"])
        residuals[code] = {"residual": rho * combined}
    return PastLeague(players), {"players": rated, "team_residuals": residuals}, asof


def _mid_pit(dist, actual):
    total = dist.sum()
    return (dist[:actual].sum() + 0.5 * dist[actual]) / total


def _rps(dist, actual):
    """Ranked probability score for a whole-number outcome: sum over k of
    (P(W <= k) - [actual <= k])^2. Proper (rewards the right center AND spread), lower is
    better, and uses the whole cumulative distribution, so it isn't noisy like the probability
    of one exact win total."""
    cdf = np.cumsum(dist) / dist.sum()
    step = (np.arange(len(dist)) >= actual).astype(float)
    return float(np.sum((cdf - step) ** 2))


def _log_prob(dist, actual):
    smoothed = dist + 0.5  # pseudo-counts: never log(0)
    return float(np.log(smoothed[actual] / smoothed.sum()))


def run_season(season, cfg):
    fold_cfg = {**cfg, "ratings": {**cfg["ratings"],
                                   "fit_target_seasons": [s for s in cfg["ratings"]["fit_target_seasons"] if s != season]}}
    fit = rt.fit(fold_cfg, write=False)
    game_fit = gm.fit(write=False, seasons=[s for s in gm.FIT_SEASONS if s != season])
    league, rated, asof = build_season(season, fit, cfg)
    games = gm.load_games(season)
    engine = Engine(league, schedule_from_results(games), cfg, n_sims=N_SIMS, team_season_sd=0.0, ratings=rated,
                    ratings_fit=fit, game_model=game_fit, division_season=season)
    actual = actual_wins(games)
    official = official_standings(season)
    playoff_teams = set(asof["playoff_teams"])
    by_sigma = {}
    for sigma_t in SIGMA_GRID:
        engine.set_team_season_sd(sigma_t)
        sim = engine.simulate()
        teams = {}
        for code in TEAM_INFO:
            t = sim["teams"][code]
            dist = np.array(t["distribution"], dtype=float)
            teams[code] = {"predicted_wins": t["mean_wins"], "actual_wins": actual[code],
                           "pit": float(_mid_pit(dist, actual[code])), "log_prob": _log_prob(dist, actual[code]),
                           "rps": _rps(dist, actual[code]),
                           "playoff_pct": t["playoff_pct"], "made_playoffs": int(code in playoff_teams),
                           "top6_pct": t["top6_pct"], "made_top6": int(official[code]["playoff_rank"] <= 6),
                           "play_in_pct": t["play_in_pct"], "made_play_in": int(7 <= official[code]["playoff_rank"] <= 10)}
        by_sigma[str(sigma_t)] = teams
    return {"season": season, "rating_fit": {"recency": fit["veterans"]["recency"],
                                             "shrink": fit["veterans"]["shrink_minutes"],
                                             "rho": fit["team_residual"]["rho"]},
            "game_model": {k: game_fit[k] for k in ("home_edge", "b2b_penalty", "sigma")},
            "by_sigma": by_sigma, "players_check": _player_check(season, league, rated, fit)}


def _player_check(season, league, rated, fit):
    """Are individual players' rating uncertainties right? Share of players (500+ minutes that
    season) whose full-season BPM lands inside their 50% / 80% predictive interval."""
    totals = load_season(season)[0]
    c = fit["uncertainty"]["c"]
    z = []
    for pid, p in league.players.items():
        rec = totals.get(name_key(p["name"]))
        if rec and rec.get("mp", 0) >= 500 and rec.get("bpm") is not None:
            sd = math.sqrt(rated["players"][pid]["se"] ** 2 + c / rec["mp"])
            z.append(abs(rec["bpm"] - rated["players"][pid]["impact"]) / sd)
    z = np.array(z)
    return {"n": int(len(z)), "inside_50": float(np.mean(z <= 0.6745)), "inside_80": float(np.mean(z <= 1.2816))}


# --- scoring --------------------------------------------------------------------------------------

def score(rows):
    """Metrics for a list of team-season rows (one sigma_t)."""
    pred = np.array([r["predicted_wins"] for r in rows])
    act = np.array([r["actual_wins"] for r in rows])
    pit = np.array([r["pit"] for r in rows])
    centred = pred - pred.mean()
    p = np.array([r["playoff_pct"] for r in rows])
    y = np.array([r["made_playoffs"] for r in rows])
    p6 = np.array([r["top6_pct"] for r in rows])
    y6 = np.array([r["made_top6"] for r in rows])
    clip = np.clip(p, 0.001, 0.999)
    return {
        "teams": len(rows),
        "win_mae": round(float(np.mean(np.abs(pred - act))), 2),
        "win_rmse": round(float(np.sqrt(np.mean((pred - act) ** 2))), 2),
        "slope": round(float(np.sum(centred * (act - act.mean())) / np.sum(centred ** 2)), 2),
        "corr": round(float(np.corrcoef(pred, act)[0, 1]), 2),
        "inside_50": round(float(np.mean((pit >= 0.25) & (pit <= 0.75))), 3),
        "inside_80": round(float(np.mean((pit >= 0.10) & (pit <= 0.90))), 3),
        "mean_log_prob": round(float(np.mean([r["log_prob"] for r in rows])), 4),
        "mean_rps": round(float(np.mean([r["rps"] for r in rows])), 4),
        "playoff_brier": round(float(np.mean((p - y) ** 2)), 4),
        "playoff_log_loss": round(float(-np.mean(y * np.log(clip) + (1 - y) * np.log(1 - clip))), 4),
        "playoff_brier_base_rate": round(float(np.mean((y.mean() - y) ** 2)), 4),
        "top6_brier": round(float(np.mean((p6 - y6) ** 2)), 4),
    }


def calibration_table(rows, key="playoff_pct", outcome="made_playoffs"):
    table = []
    for lo, hi in BUCKETS:
        sel = [r for r in rows if lo <= r[key] < hi]
        if sel:
            table.append({"bucket": f"{lo:.0%}-{min(hi, 1):.0%}", "teams": len(sel),
                          "predicted": round(float(np.mean([r[key] for r in sel])), 3),
                          "actual": round(float(np.mean([r[outcome] for r in sel])), 3)})
    return table


def _rows(results, sigma, seasons=None):
    return [{**t, "season": r["season"], "team": code}
            for r in results if seasons is None or r["season"] in seasons
            for code, t in r["by_sigma"][str(sigma)].items()]


def vegas_comparison(results, sigma):
    """Optional: compare with preseason Vegas win totals if data/vegas_win_totals.csv exists
    (columns team, season, total, source_url)."""
    if not os.path.exists(VEGAS_PATH):
        return {"status": "skipped: data/vegas_win_totals.csv not found"}
    import csv
    with open(VEGAS_PATH) as f:
        vegas = {(r["season"], r["team"]): float(r["total"]) for r in csv.DictReader(f)}
    rows = [r for r in _rows(results, sigma) if (r["season"], r["team"]) in vegas]
    if not rows:
        return {"status": "no overlapping team-seasons"}
    ours = np.mean([abs(r["predicted_wins"] - r["actual_wins"]) for r in rows])
    theirs = np.mean([abs(vegas[(r["season"], r["team"])] - r["actual_wins"]) for r in rows])
    return {"status": "ok", "teams": len(rows), "our_mae": round(float(ours), 2), "vegas_mae": round(float(theirs), 2)}


def run(cfg=None, write=True):
    cfg = cfg or load_sim_config()
    results = [run_season(s, cfg) for s in SEASONS]
    grid = {str(s): score(_rows(results, s)) for s in SIGMA_GRID}
    best = min(SIGMA_GRID, key=lambda s: grid[str(s)]["mean_rps"])
    # Leave-one-season-out: choose sigma_t on 4 seasons, score the 5th.
    loso_rows, folds = [], {}
    for held in SEASONS:
        train = [s for s in SEASONS if s != held]
        pick = min(SIGMA_GRID, key=lambda s: np.mean([r["rps"] for r in _rows(results, s, train)]))
        folds[held] = pick
        loso_rows += _rows(results, pick, [held])
    report = {
        "seasons": SEASONS, "n_sims": N_SIMS, "sigma_grid": grid, "sigma_t": best, "loso_sigma_t": folds,
        "loso": score(loso_rows), "loso_calibration": calibration_table(loso_rows),
        "at_best": score(_rows(results, best)),
        "by_season": {r["season"]: score(_rows(results, best, [r["season"]])) for r in results},
        "calibration": calibration_table(_rows(results, best)),
        "top6_calibration": calibration_table(_rows(results, best), "top6_pct", "made_top6"),
        "players_check": {r["season"]: r["players_check"] for r in results},
        "left_out_fits": {r["season"]: {"rating_fit": r["rating_fit"], "game_model": r["game_model"]} for r in results},
        "vegas": vegas_comparison(results, best),
        "note_effective_n": ("Teams in the same season share a schedule and a league, so the 150 team-seasons aren't "
                             "independent; treat coverage differences of about +/-3 points as noise, and calibration "
                             "buckets of 20-40 teams as about +/-8-10 points."),
    }
    if write:
        with open(OUT_PATH, "w") as f:
            json.dump(report, f, indent=1)
    return report, results


def write_report(r, path=os.path.join(ROOT, "reports", "backtest_nov9.md")):
    """Plain-markdown summary of the backtest (ASCII only)."""
    pct = lambda x: f"{x * 100:.0f}%"
    lines = ["# Backtest as of November 9, 2021-22 to 2025-26", "",
             f"- {len(r['seasons'])} seasons x 30 teams = 150 team-seasons, {r['n_sims']:,} simulated seasons each.",
             "- Only what was known on Nov 9 of each season; rating model, game model and sigma_t are fitted with "
             "that season left out. Player impact = pre-season prior (no early-season player BPM for past seasons).",
             f"- {r['note_effective_n']}", "",
             "## Choosing sigma_t (shared team-season error)", "",
             "| sigma_t | Win MAE | Slope | Inside 50% | Inside 80% | RPS (lower better) | Playoff Brier |",
             "|---|---|---|---|---|---|---|"]
    for s, m in r["sigma_grid"].items():
        mark = " (chosen)" if float(s) == r["sigma_t"] else ""
        lines.append(f"| {float(s):.2f}{mark} | {m['win_mae']:.2f} | {m['slope']:.2f} | {pct(m['inside_50'])} | "
                     f"{pct(m['inside_80'])} | {m['mean_rps']:.4f} | {m['playoff_brier']:.4f} |")
    lo = r["loso"]
    lines += ["", f"Leave-one-season-out choice: {', '.join(f'{k} {v}' for k, v in r['loso_sigma_t'].items())}. "
              f"Held-out results: win MAE {lo['win_mae']}, slope {lo['slope']}, inside 50% {pct(lo['inside_50'])}, "
              f"inside 80% {pct(lo['inside_80'])}, playoff Brier {lo['playoff_brier']} "
              f"(base rate {lo['playoff_brier_base_rate']}).", "",
              "## Results by season (chosen sigma_t)", "",
              "| Season | Win MAE | Slope | Inside 50% | Inside 80% | Playoff Brier |", "|---|---|---|---|---|---|"]
    for s, m in r["by_season"].items():
        lines.append(f"| {s} | {m['win_mae']:.2f} | {m['slope']:.2f} | {pct(m['inside_50'])} | {pct(m['inside_80'])} | "
                     f"{m['playoff_brier']:.4f} |")
    for title, key in (("Playoff odds calibration (made the playoffs, incl. play-in)", "calibration"),
                       ("Playoff odds calibration, sigma_t chosen leave-one-season-out", "loso_calibration"),
                       ("Top-6 odds calibration", "top6_calibration")):
        lines += ["", f"## {title}", "", "| Predicted | Teams | Avg predicted | Actual |", "|---|---|---|---|"]
        lines += [f"| {b['bucket']} | {b['teams']} | {pct(b['predicted'])} | {pct(b['actual'])} |" for b in r[key]]
    lines += ["", "## Player-level check", "",
              "Share of players (500+ minutes) whose full-season BPM landed inside their 50% / 80% predictive "
              "interval; below about 45% / 75% would mean player SEs are too small:", ""]
    lines += [f"- {s}: {pct(v['inside_50'])} / {pct(v['inside_80'])} ({v['n']} players)"
              for s, v in r["players_check"].items()]
    lines += ["", f"## Vegas comparison", "", f"- {r['vegas']['status']}"]
    if r["vegas"].get("status") == "ok":
        lines.append(f"- Our MAE {r['vegas']['our_mae']} vs Vegas {r['vegas']['vegas_mae']} over {r['vegas']['teams']} teams.")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


if __name__ == "__main__":
    import time
    t = time.time()
    r, _ = run()
    print(f"Backtest {r['seasons'][0]} to {r['seasons'][-1]} as of Nov 9 ({time.time() - t:.0f}s)")
    print("sigma_t  win MAE  slope  inside50  inside80  RPS     playoff Brier")
    for s, m in r["sigma_grid"].items():
        print(f"{float(s):6.2f}  {m['win_mae']:6.2f}  {m['slope']:5.2f}  {m['inside_50']:7.0%}  {m['inside_80']:7.0%}"
              f"  {m['mean_rps']:.4f}  {m['playoff_brier']:.4f}{'  <- best' if float(s) == r['sigma_t'] else ''}")
    print("Leave-one-season-out sigma_t:", r["loso_sigma_t"], "->", r["loso"])
    print("Players inside 50%/80%:", {s: (round(v['inside_50'], 2), round(v['inside_80'], 2)) for s, v in r["players_check"].items()})
    print("Vegas:", r["vegas"]["status"])
    print("Wrote", OUT_PATH, "and", write_report(r))
