"""Season simulation with player ratings, availability and scenarios (sim-accuracy Stages 3-4).

Per simulated season:
  1. Player impacts. Each player's impact is drawn once from N(rating, SE) (tradesim.ratings),
     then used for the whole season. No fixed point ratings.
  2. Team terms. Each team's residual gets a small random shift (the part that doesn't
     carry over from year to year: residual spread x sqrt(1 - rho^2)), plus a shared
     team-season error eps_team ~ N(0, sigma_t): one draw per team per season, for what
     moves a whole team together (players' rating errors are otherwise independent).
     sigma_t is set by tradesim.calibrate (data/model/uncertainty.json).
  3. Absences. Each player gets a games-played rate for the season (Beta around his expected
     availability) and misses that many games as one injury spell at a random point.
  4. Strength per game = full-strength rotation at the drawn impacts - the cost of everyone
     out that game (their minutes go to their backups, tradesim.rotation).
  5. Games. margin = S_home - S_away + home edge - b2b penalty + sigma x noise
     (tradesim.game_model); the home team wins if the margin is positive, i.e.
     P(home win) = Phi(expected margin / sigma). Margins give point differential.
  6. Standings. Seeds with the NBA's tiebreakers, then the play-in for seeds 7-10
     (tradesim.standings).

Every random draw is tied to the PLAYER (impacts, absences) or the TEAM (residual, by team
code) or the game (coin flips), never to a team's roster. Baseline and scenario therefore
share all of them, and differences come from the moves, not from luck.
"""
import hashlib
import json
import os

import numpy as np

from tradesim.game_model import back_to_backs, load_model, norm_cdf
from tradesim.ratings import load_fit as load_ratings_fit, load_ratings
from tradesim.rotation import apply_moves
from tradesim.simulate import CODES, INDEX, load_strength_sd
from tradesim.standings import SeasonTable, divisions, play_in, summaries

GAMES = 82
UNCERTAINTY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "model",
                                "uncertainty.json")


def load_team_season_sd(path=UNCERTAINTY_PATH):
    """sigma_t for the shared team-season error (0 until tradesim.calibrate has run)."""
    if not os.path.exists(path):
        return 0.0
    with open(path) as f:
        return json.load(f)["sigma_t"]


def _stream(seed, label):
    """A random generator for one player or team, the same in every scenario."""
    return np.random.default_rng(int.from_bytes(hashlib.sha256(f"{seed}:{label}".encode()).digest()[:8], "little"))


def team_season_errors(sigma_t, n_sims, seed):
    """Shared team-season errors, n_sims x 30. Zero-sum within each simulated season (one
    team's luck is the league's, so the league average strength doesn't drift): subtract the
    mean across the 30 teams, then scale by sqrt(30/29) so each team's SD stays sigma_t."""
    z = np.stack([_stream(seed, f"team_season:{c}").standard_normal(n_sims) for c in CODES], axis=1)
    n = len(CODES)
    return sigma_t * (z - z.mean(axis=1, keepdims=True)) * np.sqrt(n / (n - 1))


def draw_absences(player_ids, ratings, kappa, n_sims, seed):
    """{player_id: (missed_games, start_game)} arrays of length n_sims, one stream per player."""
    out = {}
    for pid in player_ids:
        p = min(max(ratings["players"][pid]["availability"], 0.02), 0.995)
        rng = _stream(seed, pid)
        rate = rng.beta(kappa * p, kappa * (1 - p), n_sims)
        missed = rng.binomial(GAMES, 1 - rate)
        start = (rng.random(n_sims) * (GAMES - missed + 1)).astype(np.int32)
        out[pid] = (missed.astype(np.int32), start)
    return out


def draw_impacts(player_ids, ratings, n_sims, seed):
    """{player_id: impact per simulated season}, drawn from N(rating, SE), one stream per player."""
    return {pid: (ratings["players"][pid]["impact"] + ratings["players"][pid]["se"]
                  * _stream(seed, f"impact:{pid}").standard_normal(n_sims)).astype(np.float32)
            for pid in player_ids}


def _team_game_index(schedule):
    """For each game, which of the home/away team's 82 games it is (schedule order)."""
    counter = {c: 0 for c in CODES}
    home_i, away_i = [], []
    for g in schedule:
        home_i.append(counter[g["home"]])
        counter[g["home"]] += 1
        away_i.append(counter[g["away"]])
        counter[g["away"]] += 1
    return np.array(home_i), np.array(away_i)


class Engine:
    """Everything shared by the baseline and the scenarios: schedule, fitted models, random
    draws. Teams whose rotation didn't change reuse their baseline strength arrays."""

    def __init__(self, league, schedule, cfg, n_sims=None, team_season_sd=None):
        self.league, self.schedule, self.cfg = league, schedule, cfg
        self.n_sims = n_sims or cfg["simulation"]["n_seasons"]
        seed = cfg["simulation"]["seed"]
        self.ratings = load_ratings()
        self.model = load_model()
        ratings_fit = load_ratings_fit()
        players = sorted(self.ratings["players"])
        self.absences = draw_absences(players, self.ratings, ratings_fit["availability"]["kappa"], self.n_sims, seed)
        self.impacts = draw_impacts(players, self.ratings, self.n_sims, seed)
        tr = ratings_fit["team_residual"]
        self.residual_sd = float(tr["residual_sd"] * np.sqrt(1 - tr["rho"] ** 2))
        self.team_season_sd = load_team_season_sd() if team_season_sd is None else team_season_sd
        team_season = team_season_errors(self.team_season_sd, self.n_sims, seed)
        self.residual_draws = {c: (self.residual_sd * _stream(seed, f"team:{c}").standard_normal(self.n_sims)
                                   + team_season[:, INDEX[c]]).astype(np.float32) for c in CODES}
        self.sim_cfg = {**cfg, "simulation": {**cfg["simulation"], "n_seasons": self.n_sims}}
        # Game noise (standard normal per game): margin = expected margin + sigma x noise.
        self.noise = np.random.default_rng(seed).standard_normal((self.n_sims, len(schedule)), dtype=np.float32)
        self.play_in_noise = np.random.default_rng(seed + 3).standard_normal((self.n_sims, 2, 3))
        self.divisions = divisions()
        self.G = np.zeros((len(CODES), len(CODES)))
        for g in schedule:
            self.G[INDEX[g["home"]], INDEX[g["away"]]] += 1
            self.G[INDEX[g["away"]], INDEX[g["home"]]] += 1
        self.home = np.array([INDEX[g["home"]] for g in schedule])
        self.away = np.array([INDEX[g["away"]] for g in schedule])
        self.home_court = np.array([0.0 if g["neutral"] else 1.0 for g in schedule], dtype=np.float32)
        b2b_home, b2b_away = back_to_backs(schedule)
        self.rest = (b2b_home - b2b_away).astype(np.float32)
        self.home_i, self.away_i = _team_game_index(schedule)
        self.home_onehot = np.zeros((len(schedule), len(CODES)), dtype=np.float32)
        self.away_onehot = np.zeros((len(schedule), len(CODES)), dtype=np.float32)
        self.home_onehot[np.arange(len(schedule)), self.home] = 1
        self.away_onehot[np.arange(len(schedule)), self.away] = 1
        self.baseline_rotations = apply_moves(league, [], cfg, self.ratings)
        self.baseline_strengths = {c: self.team_game_strengths(self.baseline_rotations[c]) for c in CODES}

    def team_game_strengths(self, rotation):
        """(n_sims x 82) strength of one team in each of its games."""
        ids = list(rotation.players)
        impacts = np.stack([self.impacts[pid] for pid in ids], axis=1)  # sims x players
        weights = np.array([rotation.minutes[pid] / 48 for pid in ids], dtype=np.float32)
        full = impacts @ weights + rotation.residual + self.residual_draws[rotation.code] - rotation.diminishing_returns()
        strengths = np.repeat(full[:, None], GAMES, axis=1).astype(np.float32)
        game = np.arange(GAMES)
        position = {pid: i for i, pid in enumerate(ids)}
        for pid in ids:
            w = rotation.absence_weights(pid)
            if not w:
                continue
            vec = np.zeros(len(ids), dtype=np.float32)
            for k, v in w.items():
                vec[position[k]] = v
            cost = impacts @ vec  # per simulated season
            missed, start = self.absences[pid]
            out = (game[None, :] >= start[:, None]) & (game[None, :] < (start + missed)[:, None])
            strengths -= cost[:, None] * out
        return strengths

    def uncertainty(self):
        """How much a team's season-average strength varies across simulated seasons, and the
        forecast error it should roughly match (tradesim.strength_check)."""
        sds = [float(np.std(s.mean(axis=1))) for s in self.baseline_strengths.values()]
        return {"season_strength_sd": round(float(np.mean(sds)), 3), "residual_sd": round(self.residual_sd, 3),
                "team_season_sd": round(self.team_season_sd, 3), "measured_forecast_sd": load_strength_sd()}

    def simulate(self, rotations=None, changed=()):
        """Simulate the season for a set of rotations; teams not in `changed` reuse the baseline."""
        strengths = dict(self.baseline_strengths)
        for code in changed:
            strengths[code] = self.team_game_strengths(rotations[code])
        stacked = np.stack([strengths[c] for c in CODES])  # 30 x sims x 82
        diff = stacked[self.home, :, self.home_i].T - stacked[self.away, :, self.away_i].T  # sims x games
        m = self.model
        margin = diff + m["home_edge"] * self.home_court - m["b2b_penalty"] * self.rest + m["sigma"] * self.noise
        home_won = (margin > 0).astype(np.float32)
        wins = np.rint(home_won @ self.home_onehot + (1 - home_won) @ self.away_onehot).astype(np.int16)
        pdiff = margin @ self.home_onehot - margin @ self.away_onehot
        last_game = {c: strengths[c][:, -1] for c in CODES}
        seeds, playoff = self._standings(home_won, pdiff, last_game)
        mean_strength = {c: float(strengths[c].mean()) for c in CODES}
        return {"teams": summaries(wins, seeds, playoff, self.sim_cfg), "wins": wins, "seeds": seeds,
                "playoff": playoff, "mean_strength": mean_strength}

    def _standings(self, home_won, pdiff, last_game):
        """Seeds (NBA tiebreakers) and playoff spots (play-in) for every simulated season."""
        n = self.n_sims
        W = np.zeros((n, len(CODES), len(CODES)), dtype=np.int16)
        won = home_won.astype(np.int16)
        for i in range(len(self.schedule)):
            W[:, self.home[i], self.away[i]] += won[:, i]
            W[:, self.away[i], self.home[i]] += 1 - won[:, i]
        seeds = np.zeros((n, len(CODES)), dtype=np.int8)
        playoff = np.zeros((n, len(CODES)), dtype=bool)
        seed = self.cfg["simulation"]["seed"]
        for s in range(n):
            table = SeasonTable(W[s], self.G, pdiff[s], self.divisions, np.random.default_rng([seed, 5, s]))
            for k, conf in enumerate(("East", "West")):
                order = table.seeds(conf)
                for rank, team in enumerate(order, 1):
                    seeds[s, INDEX[team]] = rank
                for team in order[:6]:
                    playoff[s, INDEX[team]] = True
                strength = {t: float(last_game[t][s]) for t in order[6:10]}
                for team in play_in(order, strength, self.model, self.play_in_noise[s, k]):
                    playoff[s, INDEX[team]] = True
        return seeds, playoff

    def baseline(self):
        if not hasattr(self, "_baseline"):
            self._baseline = self.simulate()
        return self._baseline

    def scenario(self, moves):
        """Simulate `moves` ([{"player", "from", "to"}]) against the baseline."""
        rotations = apply_moves(self.league, moves, self.cfg, self.ratings)
        changed = sorted(c for c in CODES if set(rotations[c].players) != set(self.baseline_rotations[c].players))
        base, scen = self.baseline(), self.simulate(rotations, changed)
        teams = {}
        for c in CODES:
            b, a = base["teams"][c], scen["teams"][c]
            teams[c] = {"before": b, "after": a, "changed_roster": c in changed,
                        "win_change": round(a["mean_wins"] - b["mean_wins"], 2),
                        "playoff_change": round(a["playoff_pct"] - b["playoff_pct"], 4),
                        "strength_before": round(base["mean_strength"][c], 2),
                        "strength_after": round(scen["mean_strength"][c], 2),
                        "full_strength_before": round(self.baseline_rotations[c].full_strength(), 2),
                        "full_strength_after": round(rotations[c].full_strength(), 2)}
        return {"changed_teams": changed, "teams": teams, "rotations": {c: rotations[c].breakdown() for c in changed}}
