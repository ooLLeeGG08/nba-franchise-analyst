"""Game lists for fitting, the backtest, and the 2026-27 simulation.

A schedule is a list of {"home", "away", "neutral"} dicts (team codes).
"""
import json
import os
import random

from tradesim.teams import TEAM_INFO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES_2025_26 = os.path.join(ROOT, "data", "raw", "2025_26", "games.json")
SCHEDULE_2026_27 = os.path.join(ROOT, "data", "raw", "2026_27", "schedule.json")
GAMES_PER_TEAM = 82


def load_results_2025_26(path=GAMES_2025_26):
    with open(path) as f:
        return json.load(f)["games"]


def actual_wins(results):
    wins = {code: 0 for code in TEAM_INFO}
    for g in results:
        wins[g["home"] if g["home_pts"] > g["away_pts"] else g["away"]] += 1
    return wins


def load_schedule_2026_27(path=SCHEDULE_2026_27, seed=0):
    """The 2026-27 schedule, filled up to 82 games per team.

    The NBA schedules 80 games per team in advance; the last 2 depend on the
    in-season tournament (6 knockout games still show "TBD" and 24 more are added
    after the group stage). Those are filled here with random same-conference
    matchups, which is how the league fills them too. The filler is fixed by `seed`
    so every run uses the same schedule.
    """
    with open(path) as f:
        raw = json.load(f)["games"]
    games = [{"home": g["home"], "away": g["away"], "neutral": False, "placeholder": False}
             for g in raw if g["home"] in TEAM_INFO and g["away"] in TEAM_INFO]
    counts = {code: 0 for code in TEAM_INFO}
    for g in games:
        counts[g["home"]] += 1
        counts[g["away"]] += 1
    rng = random.Random(seed)
    for conference in ("East", "West"):
        slots = [code for code, info in TEAM_INFO.items() if info["conference"] == conference
                 for _ in range(GAMES_PER_TEAM - counts[code])]
        if len(slots) % 2:
            raise ValueError(f"{conference}: odd number of open schedule slots")
        for _ in range(1000):
            rng.shuffle(slots)
            pairs = list(zip(slots[::2], slots[1::2]))
            if all(a != b for a, b in pairs):
                break
        else:
            raise ValueError(f"{conference}: couldn't pair open schedule slots")
        games += [{"home": a, "away": b, "neutral": False, "placeholder": True} for a, b in pairs]
    return games


def schedule_from_results(results):
    return [{"home": g["home"], "away": g["away"], "neutral": g["neutral"], "placeholder": False} for g in results]
