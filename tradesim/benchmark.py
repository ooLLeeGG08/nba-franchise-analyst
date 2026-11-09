"""Time and memory for one scenario request at a given number of simulated seasons.

Run (one process per size, so peak memory is clean):
    python -m tradesim.benchmark 4000
Prints: engine setup, baseline (simulated / from cache), scenario, total, and peak memory.
"""
import resource
import sys
import time

from tradesim.engine import Engine
from tradesim.games import load_schedule_2026_27
from tradesim.league import League
from tradesim.model import load_sim_config


def peak_mb():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1e6 if sys.platform == "darwin" else peak / 1e3  # bytes on macOS, KB on Linux


def main():
    n = int(sys.argv[1])
    use_cache = "--no-cache" not in sys.argv
    league, cfg, schedule = League.load(), load_sim_config(), load_schedule_2026_27()
    t0 = time.time()
    engine = Engine(league, schedule, cfg, n_sims=n)
    t1 = time.time()
    base = engine.baseline(use_cache=use_cache)
    t2 = time.time()
    engine.scenario([{"player": "kawhi-leonard", "from": "TOR", "to": "CLE"}])
    t3 = time.time()
    print(f"n={n:>6}  setup {t1 - t0:5.2f}s  baseline {t2 - t1:5.2f}s ({'cache' if base['from_cache'] else 'simulated'})  "
          f"scenario {t3 - t2:5.2f}s  total {t3 - t0:5.2f}s  peak memory {peak_mb():6.0f} MB")


if __name__ == "__main__":
    main()
