"""Standings, NBA tiebreakers and the play-in tournament (sim-accuracy Stage 5).

Seeding (per conference): teams are ranked by winning percentage. Ties use the NBA's
procedure (implemented here):

  Two teams tied                              Three or more teams tied
  1. Head-to-head win %                       1. Division winner
  2. Division winner                          2. Win % in games among all the tied teams
  3. Division win % (same division only)      3. Division win % (all in same division only)
  4. Conference win %                         4. Conference win %
  5. Win % vs playoff-eligible teams, own     5. Win % vs playoff-eligible teams, own
     conference                                  conference
  6. Win % vs playoff-eligible teams, other   6. Point differential
     conference
  7. Point differential
  Final fallback: random draw.

When a criterion separates some teams, each remaining tied group starts the procedure
again from the top (two-team or multi-team list, depending on its size). A criterion
that can't be applied (e.g. the teams never played each other) is skipped.

"Division winner": the team with the best record in its division; a tie for the division
lead is broken with the same procedure (without the division-winner step).
"Playoff-eligible": a team whose win % is at least the conference's 10th-best (play-in
included), counting teams tied for 10th. This is our reading of the rule; documented
in the README.

Play-in (seeds 7-10): 7 hosts 8, winner is the 7 seed. 9 hosts 10, loser is out. The
loser of 7-8 hosts the winner of 9-10; the winner is the 8 seed. Game probability uses
each team's strength in its last regular-season game plus home edge (no rest effect).
"""
import json
import os
from functools import lru_cache

import numpy as np

from tradesim.teams import TEAM_INFO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STANDINGS_DIR = os.path.join(ROOT, "data", "raw", "standings")
CODES = list(TEAM_INFO)
INDEX = {c: i for i, c in enumerate(CODES)}


@lru_cache(maxsize=None)
def official_standings(season):
    with open(os.path.join(STANDINGS_DIR, f"standings_{season}.json")) as f:
        return {t["team"]: t for t in json.load(f)["teams"]}


@lru_cache(maxsize=None)
def divisions(season="2026-27"):
    return {code: t["division"] for code, t in official_standings(season).items()}


class SeasonTable:
    """One season's results: W[i, j] = wins of team i over team j, G[i, j] = games between
    them, point differential per team. Works for a simulated or a real season."""

    def __init__(self, W, G, pdiff, division, rng):
        self.W, self.G, self.pdiff, self.division, self.rng = W, G, pdiff, division, rng
        self.wins = W.sum(axis=1)
        self.games = G.sum(axis=1)
        self.pct = dict(zip(CODES, (self.wins / self.games).tolist()))
        # With equal games for everyone (every simulated 2026-27 season), whole win counts
        # rank teams exactly; otherwise win % rounded to 9 decimals.
        if len(set(self.games.tolist())) == 1:
            self.rank_key = dict(zip(CODES, self.wins.tolist()))
        else:
            self.rank_key = {c: round(p, 9) for c, p in self.pct.items()}
        self._eligible = {}

    # --- records ---------------------------------------------------------------------------

    def pct_vs(self, team, opponents):
        i = INDEX[team]
        idx = [INDEX[o] for o in opponents if o != team]
        games = float(self.G[i, idx].sum())
        return None if games == 0 else float(self.W[i, idx].sum()) / games

    def eligible(self, conference):
        """Playoff-eligible teams: win % at least the 10th-best in the conference (ties included)."""
        if conference not in self._eligible:
            teams = [c for c in CODES if TEAM_INFO[c]["conference"] == conference]
            cutoff = sorted((self.rank_key[c] for c in teams), reverse=True)[9]
            self._eligible[conference] = [c for c in teams if self.rank_key[c] >= cutoff]
        return self._eligible[conference]

    def division_winners(self):
        if not hasattr(self, "_div_winners"):
            winners = set()
            for div in set(self.division.values()):
                teams = [c for c in CODES if self.division[c] == div]
                best = max(self.rank_key[c] for c in teams)
                leaders = [c for c in teams if self.rank_key[c] == best]
                winners.add(self.order(leaders, skip_division_winner=True)[0])
            self._div_winners = winners
        return self._div_winners

    # --- tiebreakers --------------------------------------------------------------------------

    def _criteria(self, group, skip_division_winner):
        same_division = len({self.division[c] for c in group}) == 1
        conf = TEAM_INFO[group[0]]["conference"]
        other = "West" if conf == "East" else "East"
        conf_teams = [c for c in CODES if TEAM_INFO[c]["conference"] == conf]
        div_winner = (None if skip_division_winner
                      else lambda t: 1.0 if t in self.division_winners() else 0.0)
        h2h = lambda t: self.pct_vs(t, group)
        div_pct = (lambda t: self.pct_vs(t, [c for c in CODES if self.division[c] == self.division[t]])) \
            if same_division else None
        conf_pct = lambda t: self.pct_vs(t, conf_teams)
        vs_own = lambda t: self.pct_vs(t, self.eligible(conf))
        vs_other = lambda t: self.pct_vs(t, self.eligible(other))
        pdiff = lambda t: float(self.pdiff[INDEX[t]])
        if len(group) == 2:
            return [h2h, div_winner, div_pct, conf_pct, vs_own, vs_other, pdiff]
        return [div_winner, h2h, div_pct, conf_pct, vs_own, pdiff]

    def order(self, group, skip_division_winner=False):
        """Break a tie among `group` (same win %). Returns the teams in order."""
        group = list(group)
        if len(group) <= 1:
            return group
        for criterion in self._criteria(group, skip_division_winner):
            if criterion is None:
                continue
            values = {t: criterion(t) for t in group}
            if any(v is None for v in values.values()):
                continue
            rounded = {t: round(v, 9) for t, v in values.items()}
            levels = sorted(set(rounded.values()), reverse=True)
            if len(levels) > 1:
                out = []
                for level in levels:
                    out += self.order([t for t in group if rounded[t] == level], skip_division_winner)
                return out
        shuffled = list(group)
        self.rng.shuffle(shuffled)
        return shuffled

    def seeds(self, conference):
        """Teams of `conference` in seed order 1-15."""
        teams = [c for c in CODES if TEAM_INFO[c]["conference"] == conference]
        out = []
        for level in sorted({self.rank_key[c] for c in teams}, reverse=True):
            group = [c for c in teams if self.rank_key[c] == level]
            out += group if len(group) == 1 else self.order(group)
        return out


def play_in(seeds, strength, model, z):
    """Play-in for one conference. seeds: teams in seed order; strength: {team: strength};
    z: 3 standard normal draws. Returns (seed 7, seed 8) after the play-in."""
    s7, s8, s9, s10 = seeds[6:10]

    def home_wins(home, away, zi):
        return strength[home] - strength[away] + model["home_edge"] + model["sigma"] * zi > 0

    seventh, loser_a = (s7, s8) if home_wins(s7, s8, z[0]) else (s8, s7)
    winner_b = s9 if home_wins(s9, s10, z[1]) else s10
    eighth = loser_a if home_wins(loser_a, winner_b, z[2]) else winner_b
    return seventh, eighth


def table_from_results(games, division, seed=0):
    """SeasonTable from real game results (for checking the tiebreakers against the NBA)."""
    W = np.zeros((len(CODES), len(CODES)))
    G = np.zeros((len(CODES), len(CODES)))
    pdiff = np.zeros(len(CODES))
    for g in games:
        h, a = INDEX[g["home"]], INDEX[g["away"]]
        G[h, a] += 1
        G[a, h] += 1
        if g["home_pts"] > g["away_pts"]:
            W[h, a] += 1
        else:
            W[a, h] += 1
        pdiff[h] += g["home_pts"] - g["away_pts"]
        pdiff[a] += g["away_pts"] - g["home_pts"]
    return SeasonTable(W, G, pdiff, division, np.random.default_rng(seed))


def check_against_official(season):
    """Our seeds 1-15 from the real results vs the NBA's PlayoffRank. Returns mismatches."""
    from tradesim.game_model import load_games
    official = official_standings(season)
    table = table_from_results(load_games(season), divisions(season))
    mismatches = []
    for conf in ("East", "West"):
        for seed, team in enumerate(table.seeds(conf), 1):
            if official[team]["playoff_rank"] != seed:
                mismatches.append({"conference": conf, "team": team, "ours": seed,
                                   "official": official[team]["playoff_rank"], "wins": int(table.wins[INDEX[team]])})
    return mismatches


def summaries(wins, seeds, playoff, cfg):
    """Per-team summary over simulated seasons. seeds: regular-season seed (1-15);
    playoff: made the playoffs (top 6, or won through the play-in)."""
    lo, hi = cfg["simulation"]["range_percentiles"]
    n = wins.shape[0]
    mcse_pct = lambda p: round(float(np.sqrt(p * (1 - p) / n)), 4)
    out = {}
    for c in CODES:
        w, s, p = wins[:, INDEX[c]], seeds[:, INDEX[c]], playoff[:, INDEX[c]]
        out[c] = {
            "mean_wins": round(float(w.mean()), 1),
            "range": [int(np.percentile(w, lo)), int(np.percentile(w, hi))],
            "distribution": np.bincount(w, minlength=83)[:83].tolist(),
            "seed_frequency": [round(float(np.mean(s == k)), 4) for k in range(1, 16)],
            "top6_pct": round(float(np.mean(s <= 6)), 4),
            "play_in_pct": round(float(np.mean((s >= 7) & (s <= 10))), 4),
            "playoff_pct": round(float(np.mean(p)), 4),
            "top_seed_pct": round(float(np.mean(s == 1)), 4),
        }
        t = out[c]
        # Monte Carlo standard errors (how much these numbers would move with other random draws).
        t["mcse"] = {"mean_wins": round(float(w.std() / np.sqrt(n)), 4), "playoff_pct": mcse_pct(t["playoff_pct"]),
                     "play_in_pct": mcse_pct(t["play_in_pct"]), "top_seed_pct": mcse_pct(t["top_seed_pct"])}
    return out
