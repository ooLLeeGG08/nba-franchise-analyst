"""Game model (sim-accuracy Stage 4): probit on strength difference, home court and rest.

    P(home win) = Phi( (S_home - S_away + home_edge x home_court
                        - b2b_penalty x home_on_b2b + b2b_penalty x away_on_b2b) / sigma )

S = team strength in points per 100 possessions (about points per game). Phi is the
standard normal CDF: sigma is the spread of a single game's result around the
expected margin. home_court = 0 on neutral floors (2019-20 Orlando bubble, Mexico City,
Las Vegas, abroad). A team is on a back-to-back if it played the day before.

Fitted by maximum likelihood on every regular-season game 2018-19 to 2024-25, using each
team's actual season net rating as its strength (so the game model doesn't depend on the
player model). 2025-26 is kept out for checking. A margin regression is reported as a
cross-check: it should give similar home edge, rest penalty and spread.

Run:  python -m tradesim.game_model
"""
import json
import os
from datetime import date, timedelta

import numpy as np

from tradesim.history import team_ratings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES_DIR = os.path.join(ROOT, "data", "raw", "games")
MODEL_PATH = os.path.join(ROOT, "data", "model", "game_model.json")
FIT_SEASONS = ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"]
CHECK_SEASON = "2025-26"


def norm_cdf(x):
    """Standard normal CDF, Abramowitz & Stegun 7.1.26 (error < 1.5e-7), vectorized."""
    x = np.asarray(x, dtype=np.float64)
    z = np.abs(x) / np.sqrt(2)
    t = 1 / (1 + 0.3275911 * z)
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    erf = 1 - poly * np.exp(-z * z)
    return 0.5 * (1 + np.sign(x) * erf)


def norm_pdf(x):
    return np.exp(-0.5 * np.asarray(x) ** 2) / np.sqrt(2 * np.pi)


def load_games(season):
    if season == CHECK_SEASON:
        path = os.path.join(ROOT, "data", "raw", "2025_26", "games.json")
    else:
        path = os.path.join(GAMES_DIR, f"games_{season}.json")
    with open(path) as f:
        return json.load(f)["games"]


def back_to_backs(games):
    """(home_on_b2b, away_on_b2b): 1 if that team also played the previous calendar day.
    Games without a date (schedule placeholders) count as rested."""
    played = {}
    for g in games:
        if g.get("date"):
            for team in (g["home"], g["away"]):
                played.setdefault(team, set()).add(g["date"])
    def b2b(team, day):
        if not day:
            return 0
        prev = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        return int(prev in played.get(team, ()))
    home = np.array([b2b(g["home"], g.get("date")) for g in games])
    away = np.array([b2b(g["away"], g.get("date")) for g in games])
    return home, away


def design(seasons):
    """Rows: [strength diff, home court, away_b2b - home_b2b]; target: home won; margin."""
    xs, ys, margins = [], [], []
    for season in seasons:
        games = load_games(season)
        ratings = team_ratings()[season]
        b2b_home, b2b_away = back_to_backs(games)
        for g, bh, ba in zip(games, b2b_home, b2b_away):
            d = ratings[g["home"]]["net_rating"] - ratings[g["away"]]["net_rating"]
            xs.append([d, 0.0 if g["neutral"] else 1.0, float(ba - bh)])
            ys.append(1.0 if g["home_pts"] > g["away_pts"] else 0.0)
            margins.append(g["home_pts"] - g["away_pts"])
    return np.array(xs), np.array(ys), np.array(margins, dtype=float)


def fit_probit(x, y, iterations=50):
    """Maximum likelihood probit without intercept (Fisher scoring)."""
    beta = np.zeros(x.shape[1])
    for _ in range(iterations):
        eta = x @ beta
        p = np.clip(norm_cdf(eta), 1e-10, 1 - 1e-10)
        dens = norm_pdf(eta)
        w = dens ** 2 / (p * (1 - p))
        score = x.T @ (dens * (y - p) / (p * (1 - p)))
        info = x.T @ (x * w[:, None])
        step = np.linalg.solve(info, score)
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return beta, info


def _scores(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return {"log_loss": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 4),
            "brier": round(float(np.mean((p - y) ** 2)), 4),
            "accuracy": round(float(np.mean((p > 0.5) == (y == 1))), 4)}


def fit(write=True):
    x, y, margins = design(FIT_SEASONS)
    (a, c, e), info = fit_probit(x, y)
    se = np.sqrt(np.diag(np.linalg.inv(info)))
    sigma, home_edge, b2b = 1 / a, c / a, e / a
    # Cross-check: margin = k x diff + home + b2b + noise.
    coef, *_ = np.linalg.lstsq(x, margins, rcond=None)
    noise_sd = float(np.std(margins - x @ coef))
    # Out-of-sample check on 2025-26.
    xc, yc, _ = design([CHECK_SEASON])
    per_season = {}
    for season in FIT_SEASONS:
        xs, ys, _ = design([season])
        (_, cs, _), _ = fit_probit(xs, ys)
        per_season[season] = round(float(cs / a), 2)
    result = {
        "fit_seasons": FIT_SEASONS, "games": int(len(y)),
        "home_edge": round(float(home_edge), 3), "b2b_penalty": round(float(b2b), 3), "sigma": round(float(sigma), 3),
        "standard_errors": {"home_edge": round(float(se[1] / a), 3), "b2b_penalty": round(float(se[2] / a), 3),
                            "sigma": round(float(se[0] / a ** 2), 3)},
        "fit_scores": _scores(norm_cdf(x @ np.array([a, c, e])), y),
        "check_2025_26": _scores(norm_cdf(xc @ np.array([a, c, e])), yc),
        "margin_regression": {"points_per_rating_point": round(float(coef[0]), 3), "home_edge": round(float(coef[1]), 3),
                              "b2b_penalty": round(float(coef[2]), 3), "noise_sd": round(noise_sd, 3)},
        "home_edge_by_season": per_season,
        "b2b_share": round(float(np.mean(x[:, 2] != 0)), 3),
    }
    if write:
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        with open(MODEL_PATH, "w") as f:
            json.dump(result, f, indent=1)
    return result


def load_model(path=MODEL_PATH):
    with open(path) as f:
        return json.load(f)


def win_probability(diff, home_court, home_b2b, away_b2b, model):
    """P(home win) for arrays of strength differences and flags."""
    z = (diff + model["home_edge"] * home_court - model["b2b_penalty"] * (home_b2b - away_b2b)) / model["sigma"]
    return norm_cdf(z)


if __name__ == "__main__":
    r = fit()
    print(f"Fitted on {r['games']:,} games ({r['fit_seasons'][0]} to {r['fit_seasons'][-1]}):")
    se = r["standard_errors"]
    print(f"  home edge   {r['home_edge']:.2f} pts (+/- {se['home_edge']:.2f})")
    print(f"  b2b penalty {r['b2b_penalty']:.2f} pts (+/- {se['b2b_penalty']:.2f}); {r['b2b_share']:.0%} of games have one team on a b2b")
    print(f"  sigma       {r['sigma']:.2f} pts (+/- {se['sigma']:.2f})")
    m = r["margin_regression"]
    print(f"Margin regression check: home {m['home_edge']:.2f}, b2b {m['b2b_penalty']:.2f}, noise {m['noise_sd']:.2f}")
    print("Home edge by season:", r["home_edge_by_season"])
    print(f"Scores: fit {r['fit_scores']}, 2025-26 (not used to fit) {r['check_2025_26']}")
    print(f"Wrote {MODEL_PATH}")
