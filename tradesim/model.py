"""Team strength and minutes.

Current model (sim-accuracy Stage 2): team_strength() = sum(player impact x
projected minutes / 48) + team residual, using the fitted ratings from
tradesim.ratings. Projected minutes are scaled so each roster totals 240.

Older helpers (player_value, expected_mpg, allocate_minutes, strength_from_stints)
are the first version of the model; the 2025-26 win-model fit and backtest
(tradesim.fit, tradesim.backtest) still use them until Stages 4 and 7 replace those.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_CONFIG_PATH = os.path.join(ROOT, "config", "sim.json")


def load_sim_config(path=SIM_CONFIG_PATH):
    with open(path) as f:
        return json.load(f)


def player_value(bpm, minutes, cfg):
    pv = cfg["player_value"]
    if bpm is None or not minutes:
        return pv["replacement_bpm"]
    k = pv["shrink_minutes"]
    return (bpm * minutes + pv["replacement_bpm"] * k) / (minutes + k)


def latest_stats(player):
    """2025-26 stats, or 2024-25 for players who didn't play last season, or None."""
    for key in ("stats_2025_26", "stats_2024_25"):
        st = player.get(key)
        if st and st.get("mp"):
            return st
    return None


def expected_mpg(player, cfg):
    """Expected minutes per game from the latest season played, or a default for players with no stats."""
    mc = cfg["minutes"]
    st = latest_stats(player)
    if st and st.get("mp") and st.get("g"):
        return st["mp"] / max(st["g"], mc["games_floor"])
    acq = player.get("acquired", {})
    pick = acq.get("pick") if acq.get("type") == "draft" and acq.get("draft_year") == 2026 else None
    if pick is None:
        return mc["no_stats_mpg"]["other"]
    if pick <= 5:
        return mc["no_stats_mpg"]["pick_1_5"]
    if pick <= 14:
        return mc["no_stats_mpg"]["pick_6_14"]
    if pick <= 30:
        return mc["no_stats_mpg"]["pick_15_30"]
    return mc["no_stats_mpg"]["other"]


def allocate_minutes(mpgs, cfg):
    """Give each player (highest expected minutes first) his expected minutes until
    240 are used. If the whole roster comes up short, scale everyone up.
    `mpgs` is {player_id: expected_mpg}; returns {player_id: minutes}."""
    total = cfg["minutes"]["team_minutes"]
    out, left = {}, total
    for pid, mpg in sorted(mpgs.items(), key=lambda kv: (-kv[1], kv[0])):
        give = min(mpg, left)
        out[pid] = give
        left -= give
    if left > 1e-9 and sum(out.values()) > 0:
        scale = total / sum(out.values())
        out = {pid: m * scale for pid, m in out.items()}
    return out


def team_strength(code, players, cfg, ratings=None):
    """Team strength (net rating per 100 possessions vs an average team):

        sum(player impact x minutes / 48) + team residual

    Impacts, projected minutes and the residual come from tradesim.ratings
    (data/model/player_ratings_2026_27.json). Projected minutes become a 240-minute
    rotation (tradesim.ratings.rotation_minutes: highest first, deep bench trimmed). Returns (strength, breakdown)."""
    from tradesim.ratings import load_ratings, rotation_minutes
    ratings = ratings or load_ratings()
    rated = ratings["players"]
    mpgs = {p["id"]: rated[p["id"]]["mpg_projected"] for p in players}
    minutes = rotation_minutes(mpgs, cfg["minutes"]["team_minutes"], cfg["ratings"]["max_mpg"])
    residual = ratings["team_residuals"][code]["residual"]
    breakdown, strength = [], residual
    for p in players:
        r = rated[p["id"]]
        contribution = r["impact"] * minutes[p["id"]] / 48
        strength += contribution
        breakdown.append({"id": p["id"], "name": p["name"], "impact": r["impact"], "se": r["se"],
                          "minutes": round(minutes[p["id"]], 1), "contribution": round(contribution, 2)})
    breakdown.sort(key=lambda b: -b["minutes"])
    return strength, breakdown


def league_strengths(league, cfg, teams=None):
    """Strength for every team (or just `teams`) from the league's current rosters."""
    codes = teams or list(league.teams)
    return {code: team_strength(code, league.roster(code), cfg)[0] for code in codes}


def strength_from_stints(stints, games_per_team, cfg):
    """Team strength from players' actual minutes with each team (used for fitting and the
    backtest). stints: [{"team", "bpm", "mp"}]. Minutes are divided by games x 48, so they
    add up to about 5 players per game, the same scale as allocate_minutes()."""
    repl = cfg["player_value"]["replacement_bpm"]
    out = {}
    for s in stints:
        value = player_value(s["bpm"], s["mp"], cfg)
        out[s["team"]] = out.get(s["team"], 0.0) + (value - repl) * s["mp"] / (games_per_team * 48)
    return out
