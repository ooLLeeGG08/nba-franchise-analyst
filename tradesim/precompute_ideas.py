"""Precompute trade ideas and ship them with the app (data/ideas/), so the first visit to a
team, and the first pick of one of its ideas, don't wait for a search.

    python -m tradesim.precompute_ideas                        # all 30 teams, today
    python -m tradesim.precompute_ideas CHI BKN                # some teams
    python -m tradesim.precompute_ideas --until 2027-02-04     # every day up to that date

With --until it walks day by day and only searches when no saved result is still valid on
that day (a signing becomes tradeable, a trade window or an exception runs out), so the app
stays instant through the season without a search on every date.

For each team it saves the ideas with no trades picked, then the ideas after picking each one
of those (what Choose trades asks for next). It uses the same code path as the app
(tradesim.sequence_api.plan) and no LLM, which is what runs when GROQ_API_KEY isn't set. Saved
ideas carry a validity record, so they keep being used on later dates while the search would
give the same result (tradesim.suggest.still_valid), and they're ignored after a data refresh
changes the inputs; rerun this script then.
"""
import argparse
import glob
import os
import time
from datetime import date, timedelta

import tradesim.engine as engine_module
from tradesim.engine import Engine
from tradesim.games import load_schedule_2026_27
from tradesim.league import League, load_cba
from tradesim.model import load_sim_config
from tradesim.sequence_api import plan
from tradesim.suggest import BUNDLED_DIR
from tradesim.teams import TEAM_INFO


def main(codes, until=None):
    league, cfg, cba = League.load(), load_sim_config(), load_cba()
    engine = Engine(league, load_schedule_2026_27(), cfg)
    engine.baseline()  # from the normal cache, before the cache folder is switched below
    os.makedirs(BUNDLED_DIR, exist_ok=True)
    for code in codes:  # drop this team's old files (any key, any date)
        for old in glob.glob(os.path.join(BUNDLED_DIR, f"suggestions_{code}_*.json")):
            os.remove(old)
    engine_module.CACHE_DIR = BUNDLED_DIR  # cached_suggest now reads and writes here
    start, day = time.time(), date.today()
    last = until or day
    while day <= last:
        for code in codes:
            t = time.time()
            base = plan({"team": code, "trades": []}, league, cba, engine, day)
            searched = [] if base["ideas"].get("from_cache") else ["ideas"]
            ideas = base["ideas"]["suggestions"]
            for idea in ideas:
                after = plan({"team": code, "trades": [{"id": "t0", "moves": idea["moves"]}]}, league, cba, engine, day)
                if not after["ideas"].get("from_cache"):
                    searched.append("after a pick")
            if searched:
                print(f"{day} {code}: {len(searched)} searches ({len(ideas)} ideas), {time.time() - t:.0f}s", flush=True)
        day += timedelta(days=1)
    files = glob.glob(os.path.join(BUNDLED_DIR, "*.json"))
    size = sum(os.path.getsize(f) for f in files)
    print(f"done in {(time.time() - start) / 60:.1f} min: {len(files)} files, {size / 1024:.0f} KB in {BUNDLED_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("teams", nargs="*", help="team codes (default: all 30)")
    ap.add_argument("--until", type=date.fromisoformat, help="precompute every day from today to this date")
    args = ap.parse_args()
    main([c.upper() for c in args.teams] or list(TEAM_INFO), args.until)
