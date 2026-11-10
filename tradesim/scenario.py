"""Run a roster scenario from the command line and write its report.

    python -m tradesim.scenario kawhi-leonard:TOR:CLE
    python -m tradesim.scenario --name maxey_trade tyrese-maxey:PHI:ATL jalen-johnson:ATL:PHI

Each move is player:FROM:TO (player id as in data/2026_27/league.json, or the player's
name with spaces replaced by dashes). Writes reports/scenario_<name>.csv and .md.
"""
import argparse
import time

from tradesim.engine import Engine
from tradesim.games import load_schedule_2026_27
from tradesim.league import League
from tradesim.model import load_sim_config
from tradesim.report import scenario_terminal, write_scenario_reports


def parse_moves(league, specs):
    moves = []
    for spec in specs:
        try:
            player, frm, to = spec.split(":")
        except ValueError:
            raise SystemExit(f"Bad move {spec!r}: use player:FROM:TO")
        pid = league.player_id(player)  # NBA ID, name, or "first-last"
        if pid is None:
            raise SystemExit(f"Unknown player {player!r}")
        if frm not in league.teams or to not in league.teams:
            raise SystemExit(f"Unknown team in {spec!r}")
        moves.append({"player": pid, "from": frm.upper(), "to": to.upper()})
    return moves


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("moves", nargs="+", help="player:FROM:TO")
    parser.add_argument("--name", default=None, help="report name (default: built from the moves)")
    parser.add_argument("--runs", type=int, default=None, help="simulated seasons (default: config)")
    args = parser.parse_args()
    league, cfg = League.load(), load_sim_config()
    moves = parse_moves(league, args.moves)
    start = time.time()
    engine = Engine(league, load_schedule_2026_27(), cfg, n_sims=args.runs)
    base = engine.baseline()
    result = engine.scenario(moves)
    name = args.name or "_".join(f"{m['player']}_{m['to'].lower()}" for m in moves)[:60]
    title = "Scenario: " + "; ".join(f"{league.players[m['player']]['name']} {m['from']} -> {m['to']}" for m in moves)
    paths = write_scenario_reports(result, name, title)
    print(scenario_terminal(result))
    print(f"{engine.n_sims:,} seasons in {time.time() - start:.1f}s (baseline {'from cache' if base['from_cache'] else 'simulated and cached'})")
    print("Full results:", *paths, sep="\n  ")


if __name__ == "__main__":
    main()
