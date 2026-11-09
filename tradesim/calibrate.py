"""Set the shared team-season error sigma_t (sim-accuracy Stage 4 revision).

1. Target: the latent spread of team strength the forecasts actually miss by
   (tradesim.strength_check: forecast error vs observed net rating, minus the game luck
   in those observed ratings, sigma / sqrt(games)).
2. Measure how much a team's season-average strength already varies in the simulator
   without the team-season term (player rating draws, absences, small residual).
3. sigma_t = sqrt(target^2 - that^2): the team-season term adds the missing spread.
4. Check: on the 210 team-seasons 2019-20 to 2025-26, how often the observed net rating
   falls inside the simulator's 50% and 80% intervals (predicted strength +/- the
   simulated spread plus game luck), before and after adding sigma_t.

This is a starting value; Stage 7 refits sigma_t on the full backtest (win totals and
playoff odds). Writes data/model/uncertainty.json.

Run:  python -m tradesim.calibrate
"""
import json
import math

import numpy as np

from tradesim.engine import UNCERTAINTY_PATH, Engine
from tradesim.game_model import load_model
from tradesim.games import load_schedule_2026_27
from tradesim.league import League
from tradesim.model import load_sim_config
from tradesim.strength_check import CHECK_PATH

Z = {"50%": 0.6745, "80%": 1.2816}


def coverage(errors, latent_sd, sigma):
    """Share of team-seasons whose observed net rating is inside each central interval."""
    out = {}
    for name, z in Z.items():
        inside = [abs(e["actual"] - e["predicted"]) <= z * math.sqrt(latent_sd ** 2 + sigma ** 2 / e["games"])
                  for e in errors]
        out[name] = {"inside": int(sum(inside)), "of": len(inside), "share": round(float(np.mean(inside)), 3)}
    return out


def run(write=True):
    cfg = load_sim_config()
    with open(CHECK_PATH) as f:
        check = json.load(f)
    target = check["strength_sd"]
    engine = Engine(League.load(), load_schedule_2026_27(), cfg, n_sims=4000, team_season_sd=0.0)
    without = engine.uncertainty()["season_strength_sd"]
    sigma_t = math.sqrt(max(target ** 2 - without ** 2, 0.0))
    sigma = load_model()["sigma"]
    errors = check["team_season_errors"]
    result = {
        "target_latent_sd": target,
        "sim_sd_without_team_term": without,
        "sigma_t": round(sigma_t, 3),
        "sim_sd_with_team_term": round(math.sqrt(without ** 2 + sigma_t ** 2), 3),
        "coverage_before": coverage(errors, without, sigma),
        "coverage_after": coverage(errors, math.sqrt(without ** 2 + sigma_t ** 2), sigma),
        "note": "Starting value from the variance gap; Stage 7 refits sigma_t on win totals and playoff odds.",
    }
    if write:
        with open(UNCERTAINTY_PATH, "w") as f:
            json.dump(result, f, indent=1)
    return result


def _main():
    r = run()
    print(f"Target latent spread {r['target_latent_sd']}; simulator without team term {r['sim_sd_without_team_term']}")
    print(f"sigma_t = sqrt({r['target_latent_sd']}^2 - {r['sim_sd_without_team_term']}^2) = {r['sigma_t']}")
    for label in ("coverage_before", "coverage_after"):
        c = r[label]
        print(f"{label}: 50% interval {c['50%']['inside']}/{c['50%']['of']} ({c['50%']['share']:.0%}), "
              f"80% interval {c['80%']['inside']}/{c['80%']['of']} ({c['80%']['share']:.0%})")
    print(f"Wrote {UNCERTAINTY_PATH}")


# --- leave-one-season-out checks -------------------------------------------------------------

def _fold_sigma_t(errors, sd0, sigma):
    """sigma_t from a set of team-seasons: sqrt(latent target^2 - simulator spread^2)."""
    err2 = np.mean([(e["predicted"] - e["actual"]) ** 2 for e in errors])
    luck2 = np.mean([sigma ** 2 / e["games"] for e in errors])
    target2 = max(err2 - luck2, 0.0)
    return math.sqrt(max(target2 - sd0 ** 2, 0.0))


def loso_coverage(errors, sd0, sigma):
    """Fit sigma_t on 6 seasons, check 50%/80% coverage on the 7th; pooled over the 7 folds."""
    seasons = sorted({e["season"] for e in errors})
    folds, pooled = {}, {name: [] for name in Z}
    for held in seasons:
        train = [e for e in errors if e["season"] != held]
        test = [e for e in errors if e["season"] == held]
        sigma_t = _fold_sigma_t(train, sd0, sigma)
        cov = coverage(test, math.sqrt(sd0 ** 2 + sigma_t ** 2), sigma)
        folds[held] = {"sigma_t": round(sigma_t, 3), "50%": cov["50%"]["inside"], "80%": cov["80%"]["inside"],
                       "of": cov["80%"]["of"]}
        for name in Z:
            pooled[name].append(cov[name]["inside"])
    n = len(errors)
    return {"folds": folds,
            "pooled": {name: {"inside": int(sum(v)), "of": n, "share": round(sum(v) / n, 3)} for name, v in pooled.items()}}


def actual_seeds(games):
    """Conference seed of each team from real results: win %, ties broken by head-to-head
    (two-team ties) then point differential. (The NBA's full tiebreakers come in Stage 5.)"""
    from tradesim.teams import TEAM_INFO
    wins, played, diff, h2h = {}, {}, {}, {}
    for g in games:
        home_won = g["home_pts"] > g["away_pts"]
        for team, opp, won, margin in ((g["home"], g["away"], home_won, g["home_pts"] - g["away_pts"]),
                                       (g["away"], g["home"], not home_won, g["away_pts"] - g["home_pts"])):
            wins[team] = wins.get(team, 0) + won
            played[team] = played.get(team, 0) + 1
            diff[team] = diff.get(team, 0) + margin
            h2h[(team, opp)] = h2h.get((team, opp), 0) + won
    seeds = {}
    for conf in ("East", "West"):
        teams = [t for t in TEAM_INFO if TEAM_INFO[t]["conference"] == conf]
        pct = {t: wins[t] / played[t] for t in teams}

        def key(t):
            tied = [u for u in teams if u != t and abs(pct[u] - pct[t]) < 1e-9]
            head = h2h.get((t, tied[0]), 0) - h2h.get((tied[0], t), 0) if len(tied) == 1 else 0
            return (-pct[t], -head, -diff[t])

        for rank, t in enumerate(sorted(teams, key=key), 1):
            seeds[t] = rank
    return seeds


def simulate_past_season(games, predicted, latent_sd0, sigma_t, model, n_sims, seed):
    """Team-level simulation of a past season from its pre-season forecasts: each team's
    strength = forecast + independent spread (what the player draws give, latent_sd0) +
    zero-sum team-season error (sigma_t); real schedule, fitted game model, top 6 by wins."""
    from tradesim.engine import team_season_errors
    from tradesim.game_model import back_to_backs, norm_cdf
    from tradesim.simulate import CODES, INDEX, _seeds
    rng = np.random.default_rng(seed)
    base = np.array([predicted[c] for c in CODES])
    strengths = base[None, :] + latent_sd0 * rng.standard_normal((n_sims, len(CODES))) \
        + team_season_errors(sigma_t, n_sims, seed)
    home = np.array([INDEX[g["home"]] for g in games])
    away = np.array([INDEX[g["away"]] for g in games])
    court = np.array([0.0 if g["neutral"] else 1.0 for g in games])
    b2b_h, b2b_a = back_to_backs(games)
    p = norm_cdf((strengths[:, home] - strengths[:, away] + model["home_edge"] * court
                  - model["b2b_penalty"] * (b2b_h - b2b_a)) / model["sigma"])
    home_won = rng.random(p.shape) < p
    wins = np.zeros((n_sims, len(CODES)))
    np.add.at(wins.T, home, home_won.T)
    np.add.at(wins.T, away, (~home_won).T)
    played = np.bincount(np.concatenate([home, away]), minlength=len(CODES))
    pct = wins / played[None, :]
    seeds = _seeds(np.rint(pct * 1000).astype(np.int32), {"simulation": {"seed": seed}})
    return {c: float(np.mean(seeds[:, INDEX[c]] <= 6)) for c in CODES}


BUCKETS = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0001)]


def playoff_calibration(errors, sd0, sigma, n_sims=4000):
    """Predicted top-6 odds (sigma_t fitted leave-one-season-out) vs what happened."""
    from tradesim.game_model import load_games, load_model
    model = load_model()
    rows = []
    for held in sorted({e["season"] for e in errors}):
        sigma_t = _fold_sigma_t([e for e in errors if e["season"] != held], sd0, sigma)
        test = {e["team"]: e["predicted"] for e in errors if e["season"] == held}
        games = load_games(held)
        odds = simulate_past_season(games, test, sd0, sigma_t, model, n_sims, seed=int(held[:4]))
        seeds = actual_seeds(games)
        rows += [{"season": held, "team": t, "predicted": odds[t], "made_top6": int(seeds[t] <= 6)} for t in test]
    table = []
    for lo, hi in BUCKETS:
        sel = [r for r in rows if lo <= r["predicted"] < hi]
        if sel:
            table.append({"bucket": f"{lo:.0%}-{min(hi, 1):.0%}", "teams": len(sel),
                          "predicted": round(float(np.mean([r["predicted"] for r in sel])), 3),
                          "actual": round(float(np.mean([r["made_top6"] for r in sel])), 3)})
    brier = float(np.mean([(r["predicted"] - r["made_top6"]) ** 2 for r in rows]))
    base_rate = float(np.mean([r["made_top6"] for r in rows]))
    return {"table": table, "brier": round(brier, 4),
            "brier_base_rate": round(float(np.mean([(base_rate - r["made_top6"]) ** 2 for r in rows])), 4),
            "rows": rows}


def run_checks(write=True):
    with open(CHECK_PATH) as f:
        check = json.load(f)
    with open(UNCERTAINTY_PATH) as f:
        result = json.load(f)
    sd0, sigma = result["sim_sd_without_team_term"], load_model()["sigma"]
    errors = check["team_season_errors"]
    result["loso"] = loso_coverage(errors, sd0, sigma)
    calib = playoff_calibration(errors, sd0, sigma)
    result["playoff_calibration"] = {k: v for k, v in calib.items() if k != "rows"}
    result["note_effective_n"] = ("Team-seasons in the same year share a schedule and a league, so they aren't "
                                  "independent: effective n is below 210. Treat coverage differences of about "
                                  "+/-3 percentage points as noise.")
    if write:
        with open(UNCERTAINTY_PATH, "w") as f:
            json.dump(result, f, indent=1)
    return result


def _print_checks(r):
    loso = r["loso"]
    print("Leave-one-season-out (sigma_t fitted on the other 6 seasons):")
    for season, f in loso["folds"].items():
        print(f"  {season}: sigma_t {f['sigma_t']:.2f}  inside 50%: {f['50%']}/{f['of']}  inside 80%: {f['80%']}/{f['of']}")
    p = loso["pooled"]
    print(f"  pooled: 50% interval {p['50%']['inside']}/{p['50%']['of']} ({p['50%']['share']:.0%}), "
          f"80% interval {p['80%']['inside']}/{p['80%']['of']} ({p['80%']['share']:.0%})")
    c = r["playoff_calibration"]
    print("Playoff (top-6) odds, predicted vs actual:")
    for row in c["table"]:
        print(f"  {row['bucket']:>9}: {row['teams']:3d} teams, predicted {row['predicted']:.0%}, actual {row['actual']:.0%}")
    print(f"  Brier {c['brier']} (always guessing the base rate: {c['brier_base_rate']})")


if __name__ == "__main__":
    _main()
    _print_checks(run_checks())
