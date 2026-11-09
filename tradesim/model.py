"""Step 1 of the simulator: player value, minutes, and team strength.

Player value (per 100 possessions, vs. an average player)
    BPM (Box Plus/Minus, from Basketball-Reference) estimates how many points per
    100 possessions a player adds compared with a league-average player. It's noisy
    for players with few minutes, so it's blended with replacement level:

        value = (BPM x MP + replacement x K) / (MP + K)

    MP = minutes played in 2025-26, K = shrink_minutes (250), replacement = -2.0.
    Players who didn't play in 2025-26 (e.g. injured all season) use their 2024-25
    stats instead; players with neither (2026 rookies) get the replacement value.

Team strength (net rating per 100 possessions, before centring)
    Five players are on the court, so each minute is 1/48 of a player-game:

        strength = sum over players of (value - replacement) x minutes / 48

    Minutes add up to 240 per team, so this equals the team's expected net rating
    plus a constant (5 x 2.0 = 10). Only DIFFERENCES between teams matter for win
    probability, so the constant cancels out. For display, strengths are centred so
    the league average is 0.

Minutes (the "simple documented way" to redistribute after a trade)
    Each player's expected minutes per game = last season's minutes / max(games, 20).
    Players are sorted by that number and each gets their expected minutes until the
    team's 240 are used up; the rest of the bench gets 0. When a trade removes a
    player, his minutes flow to the next players in line ("next man up"); an
    incoming player slots in by his own minutes per game.
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


def team_strength(players, cfg):
    """players: list of player dicts on one roster. Returns (strength, breakdown)."""
    repl = cfg["player_value"]["replacement_bpm"]
    mpgs = {p["id"]: expected_mpg(p, cfg) for p in players}
    minutes = allocate_minutes(mpgs, cfg)
    breakdown, strength = [], 0.0
    for p in players:
        st = latest_stats(p) or {}
        value = player_value(st.get("bpm"), st.get("mp"), cfg)
        contribution = (value - repl) * minutes[p["id"]] / 48
        strength += contribution
        breakdown.append({"id": p["id"], "name": p["name"], "value": round(value, 2),
                          "minutes": round(minutes[p["id"]], 1), "contribution": round(contribution, 2)})
    breakdown.sort(key=lambda b: -b["minutes"])
    return strength, breakdown


def league_strengths(league, cfg, teams=None):
    """Strength for every team (or just `teams`) from the league's current rosters."""
    codes = teams or list(league.teams)
    return {code: team_strength(league.roster(code), cfg)[0] for code in codes}


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
