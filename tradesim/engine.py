"""Season simulation with player availability and scenarios (sim-accuracy Stage 3).

Per simulated season:
  1. Absences. Each player gets a games-played rate for the season, drawn from a Beta
     distribution around his expected availability (spread fitted in tradesim.ratings),
     then a number of missed games, played out as one injury spell starting at a random
     game. Draws are tied to the PLAYER (seeded by his id), not his team, so a traded
     player misses the same games in the baseline and the scenario.
  2. Strength per game. strength = full-strength rotation - absence cost of everyone
     out that game (tradesim.rotation), plus a team-level offset for remaining
     uncertainty (Stage 4 moves this to individual players).
  3. Games. P(home win) from the fitted model, one biased coin flip per game.

Baseline and scenario share every random number (absences, offsets, coin flips), so
the difference between them comes from the moves, not from luck.
"""
import hashlib
import json

import numpy as np

from tradesim.fit import load_fit as load_game_fit
from tradesim.ratings import load_fit as load_ratings_fit, load_ratings
from tradesim.rotation import apply_moves
from tradesim.simulate import CODES, INDEX, _seeds, _summaries, draw_uniforms, load_strength_sd
from tradesim.teams import TEAM_INFO

GAMES = 82


def _player_seed(seed, pid):
    return int.from_bytes(hashlib.sha256(f"{seed}:{pid}".encode()).digest()[:8], "little")


def draw_absences(player_ids, ratings, kappa, n_sims, seed):
    """{player_id: (missed_games, start_game)} arrays of length n_sims, one stream per player."""
    out = {}
    for pid in player_ids:
        p = min(max(ratings["players"][pid]["availability"], 0.02), 0.995)
        rng = np.random.default_rng(_player_seed(seed, pid))
        rate = rng.beta(kappa * p, kappa * (1 - p), n_sims)
        missed = rng.binomial(GAMES, 1 - rate)
        start = (rng.random(n_sims) * (GAMES - missed + 1)).astype(np.int32)
        out[pid] = (missed.astype(np.int32), start)
    return out


def team_game_strengths(rotation, absences, n_sims):
    """(n_sims x 82) strength of one team in each of its games."""
    strengths = np.full((n_sims, GAMES), rotation.full_strength(), dtype=np.float32)
    game = np.arange(GAMES)
    for pid in rotation.players:
        cost = rotation.absence_cost(pid)
        if abs(cost) < 1e-6:
            continue
        missed, start = absences[pid]
        out = (game[None, :] >= start[:, None]) & (game[None, :] < (start + missed)[:, None])
        strengths -= np.float32(cost) * out
    return strengths


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
    """Holds everything shared by the baseline and the scenarios: schedule, fitted models,
    random numbers. Simulating a roster setup reuses the per-team strength arrays of every
    team whose rotation didn't change."""

    def __init__(self, league, schedule, cfg, n_sims=None):
        self.league, self.schedule, self.cfg = league, schedule, cfg
        self.n_sims = n_sims or cfg["simulation"]["n_seasons"]
        self.ratings = load_ratings()
        self.game_fit = load_game_fit()
        seed = cfg["simulation"]["seed"]
        kappa = load_ratings_fit()["availability"]["kappa"]
        self.absences = draw_absences(sorted(self.ratings["players"]), self.ratings, kappa, self.n_sims, seed)
        sim_cfg = {**cfg, "simulation": {**cfg["simulation"], "n_seasons": self.n_sims}}
        self.sim_cfg = sim_cfg
        self.uniforms = draw_uniforms(len(schedule), sim_cfg)
        self.home = np.array([INDEX[g["home"]] for g in schedule])
        self.away = np.array([INDEX[g["away"]] for g in schedule])
        self.neutral = np.array([g["neutral"] for g in schedule])
        self.home_i, self.away_i = _team_game_index(schedule)
        self.home_onehot = np.zeros((len(schedule), len(CODES)), dtype=np.float32)
        self.away_onehot = np.zeros((len(schedule), len(CODES)), dtype=np.float32)
        self.home_onehot[np.arange(len(schedule)), self.home] = 1
        self.away_onehot[np.arange(len(schedule)), self.away] = 1
        self.baseline_rotations = apply_moves(league, [], cfg, self.ratings)
        self.baseline_strengths = {c: team_game_strengths(self.baseline_rotations[c], self.absences, self.n_sims)
                                   for c in CODES}
        # Team-level uncertainty left after absences: the measured forecast spread minus
        # the spread absences already create (Stage 4 replaces this with player-level draws).
        total_sd = load_strength_sd()
        absence_var = float(np.mean([np.var(s.mean(axis=1)) for s in self.baseline_strengths.values()]))
        self.team_sd = float(np.sqrt(max(total_sd ** 2 - absence_var, 0.0)))
        self.absence_sd = float(np.sqrt(absence_var))
        rng = np.random.default_rng(seed + 2)
        self.offsets = rng.normal(0, self.team_sd, (self.n_sims, len(CODES))).astype(np.float32)

    def simulate(self, rotations=None, changed=()):
        """Simulate the season for a set of rotations. Teams not in `changed` reuse the
        baseline strength arrays."""
        strengths = dict(self.baseline_strengths)
        for code in changed:
            strengths[code] = team_game_strengths(rotations[code], self.absences, self.n_sims)
        stacked = np.stack([strengths[c] for c in CODES])  # 30 x sims x 82
        s_home = stacked[self.home, :, self.home_i].T + self.offsets[:, self.home]  # sims x games
        s_away = stacked[self.away, :, self.away_i].T + self.offsets[:, self.away]
        logit = self.game_fit["home"] * (~self.neutral) + self.game_fit["slope"] * (s_home - s_away)
        home_won = (self.uniforms < 1 / (1 + np.exp(-logit))).astype(np.float32)
        wins = np.rint(home_won @ self.home_onehot + (1 - home_won) @ self.away_onehot).astype(np.int16)
        seeds = _seeds(wins, self.sim_cfg)
        mean_strength = {c: float(strengths[c].mean() + self.offsets[:, INDEX[c]].mean()) for c in CODES}
        return {"teams": _summaries(wins, seeds, self.sim_cfg), "wins": wins, "seeds": seeds,
                "mean_strength": mean_strength}

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
