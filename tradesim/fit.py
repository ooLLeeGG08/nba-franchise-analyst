"""Step 2 of the simulator: fit the win-probability model on 2025-26 games.

    P(home team wins) = 1 / (1 + exp(-(home x is_home_court + slope x (S_home - S_away))))

S = team strength (net rating per 100 possessions) from tradesim.model. `home`
is the home-court edge (0 on neutral courts) and `slope` turns a strength gap
into a probability. Both are fitted by maximum likelihood (logistic regression,
Newton's method) on every 2025-26 regular-season game, then saved to
data/model/fit.json. Nothing here is hardcoded.

Run:  python -m tradesim.fit
"""
import json
import math
import os
from datetime import date

import numpy as np

from tradesim import build_data
from tradesim.games import GAMES_PER_TEAM, load_results_2025_26
from tradesim.model import load_sim_config, strength_from_stints

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIT_PATH = os.path.join(ROOT, "data", "model", "fit.json")


def strengths_2025_26(cfg):
    """2025-26 team strengths from each player's actual minutes with each team."""
    from tradesim.history import load_season
    stints = load_season("2025-26")[1]
    return strength_from_stints(stints, GAMES_PER_TEAM, cfg)


def design_matrix(games, strengths):
    x = np.array([[0.0 if g["neutral"] else 1.0, strengths[g["home"]] - strengths[g["away"]]] for g in games])
    return x


def fit_logistic(x, y, iterations=25):
    """Logistic regression without intercept (an even matchup on a neutral court is 50/50)."""
    beta = np.zeros(x.shape[1])
    for _ in range(iterations):
        p = 1 / (1 + np.exp(-x @ beta))
        w = p * (1 - p)
        hessian = x.T @ (x * w[:, None])
        step = np.linalg.solve(hessian, x.T @ (y - p))
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return beta


def log_loss(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit(cfg=None, write=True):
    cfg = cfg or load_sim_config()
    games = load_results_2025_26()
    strengths = strengths_2025_26(cfg)
    x = design_matrix(games, strengths)
    y = np.array([1.0 if g["home_pts"] > g["away_pts"] else 0.0 for g in games])
    home, slope = fit_logistic(x, y, cfg["fit"]["newton_iterations"])
    p = 1 / (1 + np.exp(-(x @ np.array([home, slope]))))
    home_only_rate = y[x[:, 0] == 1].mean()
    p_home_only = np.where(x[:, 0] == 1, home_only_rate, 0.5)
    mean = sum(strengths.values()) / len(strengths)
    result = {
        "season": cfg["fit"]["season"],
        "fitted_on": date.today().isoformat(),
        "home": float(home),
        "slope": float(slope),
        "games": len(games),
        "log_loss": log_loss(p, y),
        "log_loss_home_court_only": log_loss(p_home_only, y),
        "accuracy": float(np.mean((p > 0.5) == (y == 1))),
        "home_win_prob_even_teams": 1 / (1 + math.exp(-home)),
        "strengths_2025_26": {k: round(v - mean, 2) for k, v in sorted(strengths.items())},
        "player_value_settings": cfg["player_value"],
    }
    if write:
        os.makedirs(os.path.dirname(FIT_PATH), exist_ok=True)
        with open(FIT_PATH, "w") as f:
            json.dump(result, f, indent=1)
    return result


def load_fit(path=FIT_PATH):
    with open(path) as f:
        return json.load(f)


if __name__ == "__main__":
    r = fit()
    print(f"home court: {r['home']:.3f} (even teams at home win {r['home_win_prob_even_teams']:.1%})")
    print(f"slope: {r['slope']:.4f} per point of net rating")
    print(f"log loss {r['log_loss']:.4f} vs {r['log_loss_home_court_only']:.4f} with home court only; "
          f"picks the winner {r['accuracy']:.1%} of the time")
    print(f"Wrote {FIT_PATH}")
