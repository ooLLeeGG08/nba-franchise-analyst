"""Game model: logistic regression on strength difference, home court and rest.

    log(p / (1 - p)) = b_s x (S_home - S_away) + b_h x home_court + b_r x (away_on_b2b - home_on_b2b)
    p = P(home win) = 1 / (1 + exp(-log-odds))

S = team strength in points per 100 possessions (about points per game). home_court = 0
on neutral floors (2019-20 Orlando bubble, Mexico City, Las Vegas, abroad). A team is on
a back-to-back if it played the day before. There is no intercept: two equal, rested
teams on a neutral floor are a coin flip.

In points: scale = 1 / b_s, home_edge = b_h / b_s, b2b_penalty = b_r / b_s, so
p = 1 / (1 + exp(-(S_home - S_away + home_edge x home_court - b2b_penalty x rest) / scale)).
The simulator draws each game's margin as that expected margin plus scale x a standard
logistic draw, so the home team wins exactly with probability p (noise SD = scale x pi / sqrt 3).

Fitted by maximum likelihood (Newton's method) on every regular-season game 2018-19 to
2024-25, using each team's actual season net rating as its strength (so the game model
doesn't depend on the player model). 2025-26 is kept out for checking. Also reported:
log-likelihood vs the base-rate-only model, McFadden's pseudo-R^2 and the likelihood-ratio
chi^2, and a margin regression as a cross-check of home edge and rest penalty.

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


def logistic(x):
    return 1 / (1 + np.exp(-np.asarray(x, dtype=np.float64)))


def logistic_from_normal(z):
    """Standard logistic draws from standard normal ones (through their shared uniform), so the
    simulator keeps its normal random streams but games follow the logistic model."""
    u = np.clip(norm_cdf(z), 1e-12, 1 - 1e-12)
    return np.log(u) - np.log1p(-u)


def fit_logistic(x, y, iterations=50):
    """Maximum likelihood logistic regression without intercept (Newton's method).
    Returns (coefficients, covariance matrix)."""
    beta = np.zeros(x.shape[1])
    for _ in range(iterations):
        p = logistic(x @ beta)
        w = p * (1 - p)
        info = x.T @ (x * w[:, None])
        step = np.linalg.solve(info, x.T @ (y - p))
        beta += step
        if np.max(np.abs(step)) < 1e-12:
            break
    p = logistic(x @ beta)
    info = x.T @ (x * (p * (1 - p))[:, None])
    return beta, np.linalg.inv(info)


def log_likelihood(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def likelihood_ratio(p, y, added_parameters=2):
    """LL of the model vs the base-rate-only model (every game = the overall home win rate):
    McFadden's pseudo-R^2 and chi^2 = 2 (LL_fit - LL_overall) with its p-value. The model has
    3 parameters, the base-rate model 1, so df = 2 (p-value exp(-chi^2 / 2), exact for df = 2)."""
    ll_fit = log_likelihood(p, y)
    ll_overall = log_likelihood(np.full_like(y, y.mean()), y)
    chi2 = 2 * (ll_fit - ll_overall)
    return {"LL_fit": round(ll_fit, 1), "LL_overall": round(ll_overall, 1), "home_win_rate": round(float(y.mean()), 4),
            "mcfadden_r2": round(1 - ll_fit / ll_overall, 4), "chi2": round(chi2, 1), "df": added_parameters,
            "p_value": float(np.exp(-chi2 / 2)) if added_parameters == 2 else None}


def _in_points(beta, cov):
    """(scale, home_edge, b2b_penalty) and their standard errors (delta method)."""
    a, c, e = beta
    out, se = {"scale": 1 / a, "home_edge": c / a, "b2b_penalty": e / a}, {}
    grads = {"scale": np.array([-1 / a ** 2, 0, 0]), "home_edge": np.array([-c / a ** 2, 1 / a, 0]),
             "b2b_penalty": np.array([-e / a ** 2, 0, 1 / a])}
    for k, g in grads.items():
        se[k] = float(np.sqrt(g @ cov @ g))
    return out, se


def _scores(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return {"log_loss": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 4),
            "brier": round(float(np.mean((p - y) ** 2)), 4),
            "accuracy": round(float(np.mean((p > 0.5) == (y == 1))), 4)}


def fit(write=True, seasons=None):
    seasons = seasons or FIT_SEASONS
    x, y, margins = design(seasons)
    beta, cov = fit_logistic(x, y)
    pts, pts_se = _in_points(beta, cov)
    coef_se = np.sqrt(np.diag(cov))
    # Cross-check: margin = k x diff + home + b2b + noise.
    coef, *_ = np.linalg.lstsq(x, margins, rcond=None)
    noise_sd = float(np.std(margins - x @ coef))
    # Out-of-sample check on 2025-26.
    xc, yc, _ = design([CHECK_SEASON])
    per_season = {}
    for season in seasons:
        xs, ys, _ = design([season])
        b, _ = fit_logistic(xs, ys)
        per_season[season] = round(float(b[1] / beta[0]), 2)
    p_fit, p_check = logistic(x @ beta), logistic(xc @ beta)
    result = {
        "family": "logistic",
        "fit_seasons": list(seasons), "games": int(len(y)),
        "coefficients": {"strength": round(float(beta[0]), 5), "home_court": round(float(beta[1]), 5),
                         "rest": round(float(beta[2]), 5)},
        "coefficient_standard_errors": {"strength": round(float(coef_se[0]), 5),
                                        "home_court": round(float(coef_se[1]), 5), "rest": round(float(coef_se[2]), 5)},
        "home_edge": round(pts["home_edge"], 3), "b2b_penalty": round(pts["b2b_penalty"], 3),
        "scale": round(pts["scale"], 3), "noise_sd": round(pts["scale"] * np.pi / np.sqrt(3), 3),
        "standard_errors": {k: round(v, 3) for k, v in pts_se.items()},
        "likelihood": likelihood_ratio(p_fit, y),
        "likelihood_check_2025_26": likelihood_ratio(p_check, yc),
        "fit_scores": _scores(p_fit, y),
        "check_2025_26": _scores(p_check, yc),
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
    expected = diff + model["home_edge"] * home_court - model["b2b_penalty"] * (home_b2b - away_b2b)
    return logistic(expected / model["scale"])


if __name__ == "__main__":
    r = fit()
    print(f"Logistic regression on {r['games']:,} games ({r['fit_seasons'][0]} to {r['fit_seasons'][-1]}):")
    print(f"  log-odds = {r['coefficients']['strength']} x strength gap + {r['coefficients']['home_court']} x home "
          f"+ {r['coefficients']['rest']} x rest")
    se = r["standard_errors"]
    print(f"  home edge   {r['home_edge']:.2f} pts (+/- {se['home_edge']:.2f})")
    print(f"  b2b penalty {r['b2b_penalty']:.2f} pts (+/- {se['b2b_penalty']:.2f}); {r['b2b_share']:.0%} of games have one team on a b2b")
    print(f"  scale       {r['scale']:.2f} pts (+/- {se['scale']:.2f}); game noise SD {r['noise_sd']:.2f}")
    lk, lc = r["likelihood"], r["likelihood_check_2025_26"]
    print(f"  LL {lk['LL_fit']} vs base rate {lk['LL_overall']}: McFadden R^2 {lk['mcfadden_r2']}, chi^2 {lk['chi2']} "
          f"(df {lk['df']}, p = {lk['p_value']:.1e}); 2025-26 McFadden R^2 {lc['mcfadden_r2']}")
    m = r["margin_regression"]
    print(f"Margin regression check: home {m['home_edge']:.2f}, b2b {m['b2b_penalty']:.2f}, noise {m['noise_sd']:.2f}")
    print("Home edge by season:", r["home_edge_by_season"])
    print(f"Scores: fit {r['fit_scores']}, 2025-26 (not used to fit) {r['check_2025_26']}")
    print(f"Wrote {MODEL_PATH}")
