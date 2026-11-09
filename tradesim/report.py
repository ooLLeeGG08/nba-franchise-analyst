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
           "playoff_pct", "play_in_pct", "top_seed_pct"]


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
                        "top_seed_pct": float(r["top_seed_pct"])})
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
