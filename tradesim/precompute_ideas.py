"""Precompute trade ideas and ship them with the app (data/ideas/): every team's 4 starting
ideas, and the ideas after picking each one of them, so neither waits for a search.

    python -m tradesim.precompute_ideas            # all 30 teams
    python -m tradesim.precompute_ideas CHI BKN    # some teams

The app checks and searches trades as of the data's date (league.json `as_of`, see server.py
_as_of), so the starting ideas are fixed until the data is refreshed. Rerun this script after
a refresh: saved ideas no longer match once the inputs change. It uses the same code path as
the app (tradesim.sequence_api.plan) and no LLM, which is what runs without GROQ_API_KEY.
"""
import glob
import os
import sys
import time
from datetime import date

import tradesim.engine as engine_module
from tradesim.engine import Engine
from tradesim.games import load_schedule_2026_27
from tradesim.league import League, load_cba
from tradesim.model import load_sim_config
from tradesim.sequence_api import plan
from tradesim.suggest import BUNDLED_DIR
from tradesim.teams import TEAM_INFO


def main(codes):
    league, cfg, cba = League.load(), load_sim_config(), load_cba()
    engine = Engine(league, load_schedule_2026_27(), cfg)
    engine.baseline()  # from the normal cache, before the cache folder is switched below
    day = date.fromisoformat(league.as_of)
    os.makedirs(BUNDLED_DIR, exist_ok=True)
    for code in codes:  # drop this team's old files (any key, any date)
        for old in glob.glob(os.path.join(BUNDLED_DIR, f"suggestions_{code}_*.json")):
            os.remove(old)
    engine_module.CACHE_DIR = BUNDLED_DIR  # cached_suggest now reads and writes here
    start = time.time()
    for n, code in enumerate(codes, 1):
        t = time.time()
        base = plan({"team": code, "trades": []}, league, cba, engine, day)
        ideas = base["ideas"]["suggestions"]
        for idea in ideas:
            plan({"team": code, "trades": [{"id": "t0", "moves": idea["moves"]}]}, league, cba, engine, day)
        print(f"[{n}/{len(codes)}] {code}: {len(ideas)} starting ideas + {len(ideas)} after-pick searches "
              f"as of {day}, {time.time() - t:.0f}s", flush=True)
    files = glob.glob(os.path.join(BUNDLED_DIR, "*.json"))
    size = sum(os.path.getsize(f) for f in files)
    print(f"done in {(time.time() - start) / 60:.1f} min: {len(files)} files, {size / 1024:.0f} KB in {BUNDLED_DIR}")


if __name__ == "__main__":
    main([c.upper() for c in sys.argv[1:]] or list(TEAM_INFO))
