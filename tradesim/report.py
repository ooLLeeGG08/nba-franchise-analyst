"""Write simulation results to files that survive copy/paste.

The terminal table broke when pasted elsewhere (line wrapping, special characters),
so results are written as:
  reports/<name>.csv  one row per team, raw numbers (for spreadsheets/other tools)
  reports/<name>.md   plain markdown tables, ASCII only, one per conference
The terminal only shows a compact summary. This module only formats; it never
changes the numbers.
"""
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(ROOT, "reports")

COLUMNS = ["conference", "rank", "team", "strength", "mean_wins", "range_low", "range_high",
           "playoff_pct", "play_in_pct", "top_seed_pct",
           "mean_wins_mcse", "playoff_pct_mcse", "play_in_pct_mcse", "top_seed_pct_mcse"]


def ranked_rows(rows):
    """Sort within each conference by average wins (high to low), ties by team code, and
    add a 1-15 rank. One sort rule everywhere, so the CSV, markdown and terminal agree."""
    out = []
    for conference in ("East", "West"):
        conf_rows = sorted((r for r in rows if r["conference"] == conference),
                           key=lambda r: (-r["mean_wins"], r["team"]))
        for rank, r in enumerate(conf_rows, 1):
            out.append({"conference": conference, "rank": rank, "team": r["team"],
                        "strength": float(r["strength"]), "mean_wins": float(r["mean_wins"]),
                        "range_low": int(r["range"][0]), "range_high": int(r["range"][1]),
                        "playoff_pct": float(r["playoff_pct"]), "play_in_pct": float(r["play_in_pct"]),
                        "top_seed_pct": float(r["top_seed_pct"]),
                        **{f"{k}_mcse": float(r.get("mcse", {}).get(k, 0.0))
                           for k in ("mean_wins", "playoff_pct", "play_in_pct", "top_seed_pct")}})
    return out


def _pct(x):
    return f"{x * 100:.0f}%"


def markdown(rows, title, notes=()):
    lines = [f"# {title}", ""]
    lines += [f"- {n}" for n in notes]
    for conference in ("East", "West"):
        lines += ["", f"## {conference}", "",
                  "| # | Team | Strength | Avg wins | Range (10-90%) | Playoff | Play-in | #1 seed |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in (r for r in rows if r["conference"] == conference):
            lines.append(f"| {r['rank']} | {r['team']} | {r['strength']:+.1f} | {r['mean_wins']:.1f} | "
                         f"{r['range_low']}-{r['range_high']} | {_pct(r['playoff_pct'])} | "
                         f"{_pct(r['play_in_pct'])} | {_pct(r['top_seed_pct'])} |")
    return "\n".join(lines) + "\n"


def write_reports(rows, name, title, notes=(), directory=REPORTS_DIR):
    """Write reports/<name>.csv and reports/<name>.md. Returns the two paths."""
    ranked = ranked_rows(rows)
    os.makedirs(directory, exist_ok=True)
    csv_path = os.path.join(directory, f"{name}.csv")
    md_path = os.path.join(directory, f"{name}.md")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(ranked)
    with open(md_path, "w") as f:
        f.write(markdown(ranked, title, notes))
    return csv_path, md_path


def terminal_summary(rows):
    """Compact plain-text table: about 50 characters wide, so it doesn't wrap."""
    lines = []
    for conference in ("East", "West"):
        lines.append(f"{conference:<5} Team   Str  Wins  Range  PO%  PI%  #1%")
        for r in (r for r in ranked_rows(rows) if r["conference"] == conference):
            lines.append(f"{r['rank']:>4}  {r['team']:<4} {r['strength']:+5.1f} {r['mean_wins']:5.1f} "
                         f"{r['range_low']:>2}-{r['range_high']:<2} {r['playoff_pct'] * 100:4.0f} "
                         f"{r['play_in_pct'] * 100:4.0f} {r['top_seed_pct'] * 100:4.0f}")
        lines.append("")
    return "\n".join(lines)


# --- scenario reports ------------------------------------------------------------------------

SCENARIO_COLUMNS = ["conference", "team", "changed_roster", "moved",
                    "wins_before", "wins_after", "wins_change", "wins_change_mcse",
                    "playoff_before", "playoff_after", "playoff_change", "playoff_change_mcse",
                    "play_in_before", "play_in_after", "play_in_change", "play_in_change_mcse",
                    "top_seed_before", "top_seed_after", "top_seed_change", "top_seed_change_mcse",
                    "range_before", "range_after"]


def scenario_rows(result):
    from tradesim.teams import TEAM_INFO
    rows = []
    for code, t in result["teams"].items():
        b, a, d = t["before"], t["after"], t["delta"]
        rows.append({"conference": TEAM_INFO[code]["conference"], "team": code,
                     "changed_roster": t["changed_roster"], "moved": t["moved"],
                     "wins_before": b["mean_wins"], "wins_after": a["mean_wins"],
                     "wins_change": d["mean_wins"]["change"], "wins_change_mcse": d["mean_wins"]["mcse"],
                     "playoff_before": b["playoff_pct"], "playoff_after": a["playoff_pct"],
                     "playoff_change": d["playoff_pct"]["change"], "playoff_change_mcse": d["playoff_pct"]["mcse"],
                     "play_in_before": b["play_in_pct"], "play_in_after": a["play_in_pct"],
                     "play_in_change": d["play_in_pct"]["change"], "play_in_change_mcse": d["play_in_pct"]["mcse"],
                     "top_seed_before": b["top_seed_pct"], "top_seed_after": a["top_seed_pct"],
                     "top_seed_change": d["top_seed_pct"]["change"], "top_seed_change_mcse": d["top_seed_pct"]["mcse"],
                     "range_before": f"{b['range'][0]}-{b['range'][1]}", "range_after": f"{a['range'][0]}-{a['range'][1]}"})
    return sorted(rows, key=lambda r: (not r["changed_roster"], not r["moved"], r["conference"], -r["wins_after"]))


def _signed(x, digits=1):
    return f"{x:+.{digits}f}"


def _pts(x):
    return f"{x * 100:+.1f}"


def scenario_markdown(result, title):
    rows = scenario_rows(result)
    lines = [f"# {title}", "", "Moves:"]
    lines += [f"- {m['player']}: {m['from']} -> {m['to']}" for m in result["moves"]]
    lines += ["", f"{result['n_sims']:,} simulated seasons each, sharing every random draw, so the changes are "
              "paired. Change = scenario - baseline, +/- its Monte Carlo SE. Percent changes are in points.",
              "Flag: ** = roster changed; * = other team with a change beyond 2 SE and at least 0.5 wins or "
              "2 points of playoff / play-in / #1-seed odds (config: simulation.highlight).", "",
              "| Flag | Team | Avg wins | Change | Range | Playoff % | Change (pts) | Play-in % | Change (pts) "
              "| #1 seed % | Change (pts) |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        flag = "**" if r["changed_roster"] else ("*" if r["moved"] else "")
        lines.append(
            f"| {flag} | {r['team']} | {r['wins_before']:.1f} -> {r['wins_after']:.1f} | "
            f"{_signed(r['wins_change'], 2)} +/- {r['wins_change_mcse']:.2f} | {r['range_before']} -> {r['range_after']} | "
            f"{r['playoff_before'] * 100:.0f} -> {r['playoff_after'] * 100:.0f} | "
            f"{_pts(r['playoff_change'])} +/- {r['playoff_change_mcse'] * 100:.1f} | "
            f"{r['play_in_before'] * 100:.0f} -> {r['play_in_after'] * 100:.0f} | "
            f"{_pts(r['play_in_change'])} +/- {r['play_in_change_mcse'] * 100:.1f} | "
            f"{r['top_seed_before'] * 100:.0f} -> {r['top_seed_after'] * 100:.0f} | "
            f"{_pts(r['top_seed_change'])} +/- {r['top_seed_change_mcse'] * 100:.1f} |")
    return "\n".join(lines) + "\n"


def write_scenario_reports(result, name, title, directory=REPORTS_DIR):
    os.makedirs(directory, exist_ok=True)
    csv_path = os.path.join(directory, f"scenario_{name}.csv")
    md_path = os.path.join(directory, f"scenario_{name}.md")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SCENARIO_COLUMNS)
        writer.writeheader()
        writer.writerows(scenario_rows(result))
    with open(md_path, "w") as f:
        f.write(scenario_markdown(result, title))
    return csv_path, md_path


def scenario_terminal(result):
    """Compact summary: flagged teams only."""
    lines = ["Team  Wins (chg +/- SE)    Playoff% (chg pts)"]
    for r in scenario_rows(result):
        if not r["moved"]:
            continue
        flag = "**" if r["changed_roster"] else "* "
        lines.append(f"{flag}{r['team']:<4} {r['wins_after']:5.1f} ({_signed(r['wins_change'], 2)} +/- "
                     f"{r['wins_change_mcse']:.2f})  {r['playoff_after'] * 100:3.0f} ({_pts(r['playoff_change'])})")
    return "\n".join(lines)
