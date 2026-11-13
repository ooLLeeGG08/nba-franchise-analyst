"""Numbers for the README's "How the simulation works" section (nothing here changes the model).

    python scripts/model_metrics.py

1. Team strength (step 1): R^2 = (SS_mean - SS_fit) / SS_mean of the projected team strength
   vs the observed net rating on the 210 team-seasons in data/model/strength_check.json. It's a
   check of a computed rating (minutes-weighted player impacts), not a fitted regression.
2. Game model (step 2, logistic regression): coefficients, log-likelihood of the fit and of
   the base-rate-only model, McFadden's pseudo-R^2 and the likelihood-ratio chi^2 with its
   p-value, on the training games (2018-19 to 2024-25) and on 2025-26 (held out).
3. A worked example with the 2026-27 projected strengths (BKN vs BOS).
4. Simulation error: SD of a team's simulated wins / sqrt(10,000).
"""
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tradesim import game_model as gm  # noqa: E402


def main():
    out = {}

    # 1. Projected team strength vs observed net rating
    sc = json.load(open(os.path.join(ROOT, "data/model/strength_check.json")))
    pred = np.array([e["predicted"] for e in sc["team_season_errors"]])
    act = np.array([e["actual"] for e in sc["team_season_errors"]])
    ss_mean = float(np.sum((act - act.mean()) ** 2))
    ss_fit = float(np.sum((act - pred) ** 2))
    out["step1_team_strength_check"] = {"team_seasons": int(len(act)), "SS_mean": round(ss_mean, 1),
                                        "SS_fit": round(ss_fit, 1), "R2": round((ss_mean - ss_fit) / ss_mean, 3),
                                        "rmse": round(math.sqrt(ss_fit / len(act)), 2)}

    # 2. Logistic game model, refitted here from the game data
    x, y, _ = gm.design(gm.FIT_SEASONS)
    beta, cov = gm.fit_logistic(x, y)
    xc, yc, _ = gm.design([gm.CHECK_SEASON])
    out["step2_logistic"] = {
        "coefficients": {"strength_gap": round(float(beta[0]), 5), "home_court": round(float(beta[1]), 5),
                         "rest": round(float(beta[2]), 5)},
        "standard_errors": [round(float(v), 5) for v in np.sqrt(np.diag(cov))],
        "train_2018_19_to_2024_25": {"games": int(len(y)), **gm.likelihood_ratio(gm.logistic(x @ beta), y)},
        "held_out_2025_26": {"games": int(len(yc)), **gm.likelihood_ratio(gm.logistic(xc @ beta), yc)},
    }

    # 3. Worked example with the 2026-27 projected strengths (season averages in the simulator)
    sys.path.insert(0, ROOT)
    from server import _sim
    s = _sim()
    base = s["engine"].baseline()
    strength = base["mean_strength"]
    example = {}
    for home, away in (("BKN", "BOS"), ("BOS", "BKN")):
        gap = strength[home] - strength[away]
        log_odds = beta[0] * gap + beta[1]
        example[f"{home} home vs {away}"] = {"S_home": round(strength[home], 2), "S_away": round(strength[away], 2),
                                             "gap": round(gap, 2), "log_odds": round(float(log_odds), 3),
                                             "p_home_win": round(float(gm.logistic(log_odds)), 3)}
    out["step2_worked_example"] = example

    # 4. Simulation error of mean wins
    mcse = {c: t["mcse"]["mean_wins"] for c, t in base["teams"].items()}
    vals = sorted(mcse.values())
    i = list(base["teams"]).index("BKN")
    out["step3_mcse_mean_wins"] = {"n_seasons": int(base["wins"].shape[0]), "min": vals[0],
                                   "median": vals[len(vals) // 2], "max": vals[-1],
                                   "BKN_sd": round(float(base["wins"][:, i].std()), 2), "BKN_mcse": mcse["BKN"]}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
