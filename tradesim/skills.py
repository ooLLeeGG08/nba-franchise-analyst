"""Skill profiles from Basketball-Reference advanced stats (for trade suggestions).

The LLM may only ask for skills from SKILLS; each is a measurable blend of stats, scored
as a percentile (0-100) among players with 500+ minutes in their latest season:

  shooting           3-point attempt rate + true shooting %
  rim protection     block % + defensive BPM (half weight)
  rebounding         total rebound %
  playmaking         assist % - turnover % (half weight)
  perimeter defense  steal % + defensive BPM (half weight)
  scoring            usage % + true shooting % + offensive BPM (half weight)

A team's skill level = its rotation players' percentiles weighted by expected minutes.
"""
from functools import lru_cache

import numpy as np

SKILLS = {
    "shooting": {"3par": 1.0, "ts_pct": 1.0},
    "rim protection": {"blk_pct": 1.0, "dbpm": 0.5},
    "rebounding": {"trb_pct": 1.0},
    "playmaking": {"ast_pct": 1.0, "tov_pct": -0.5},
    "perimeter defense": {"stl_pct": 1.0, "dbpm": 0.5},
    "scoring": {"usg_pct": 1.0, "ts_pct": 1.0, "obpm": 0.5},
}
MIN_MINUTES = 500


def latest_line(player):
    """2025-26 stats, else 2024-25 (players who missed last season), else None."""
    for key in ("stats_2025_26", "stats_2024_25"):
        st = player.get(key)
        if st and st.get("mp"):
            return st
    return None


@lru_cache(maxsize=4)
def _population(league_id):
    from tradesim.league import League
    league = League.load() if league_id == "default" else None
    lines = [latest_line(p) for p in league.players.values()]
    lines = [l for l in lines if l and l["mp"] >= MIN_MINUTES]
    stats = sorted({s for spec in SKILLS.values() for s in spec})
    values = {s: np.array([l.get(s) if l.get(s) is not None else np.nan for l in lines], dtype=float) for s in stats}
    moments = {s: (np.nanmean(v), np.nanstd(v)) for s, v in values.items()}
    raw = {skill: _raw(lines_values={s: values[s] for s in spec}, spec=spec, moments=moments)
           for skill, spec in SKILLS.items()}
    return moments, {skill: np.sort(r[~np.isnan(r)]) for skill, r in raw.items()}


def _raw(lines_values, spec, moments):
    total = 0.0
    for stat, weight in spec.items():
        mean, sd = moments[stat]
        total = total + weight * (lines_values[stat] - mean) / sd
    return total


def player_skills(player, league_id="default"):
    """{skill: percentile 0-100} for one player, or {} if he has no usable stats."""
    line = latest_line(player)
    if not line:
        return {}
    moments, sorted_raw = _population(league_id)
    out = {}
    for skill, spec in SKILLS.items():
        if any(line.get(s) is None for s in spec):
            continue
        raw = _raw({s: line[s] for s in spec}, spec, moments)
        pop = sorted_raw[skill]
        out[skill] = round(float(100.0 * np.searchsorted(pop, raw, side="right") / len(pop)), 1)
    return out


def team_skills(rotation, league, expected_minutes):
    """{skill: minutes-weighted percentile} for a team's rotation."""
    totals = {s: [0.0, 0.0] for s in SKILLS}
    for pid, minutes in expected_minutes.items():
        if minutes <= 0:
            continue
        for skill, pctl in player_skills(league.players[pid]).items():
            totals[skill][0] += pctl * minutes
            totals[skill][1] += minutes
    return {s: round(v / w, 1) if w else 50.0 for s, (v, w) in totals.items()}
