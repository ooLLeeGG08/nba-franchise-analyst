# Team Roster & Trade History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the chatbot real, verified data on team rosters (every player, every team, every season 2015-16 through 2025-26) and notable trade history, so it can answer roster and trade questions grounded in fact instead of saying "I don't have that."

**Architecture:** A new fetch script pulls full rosters live via `nba_api` (matching the existing `fetch_nba_data.py` pattern) into `data/team_rosters.json`. `rag.py` gains `resolve_season(message, history)` (mirroring the existing `resolve_team`) to pick which season's roster to surface, and `_team_document`/`retrieve_context` become season-aware. Trade history is hand-researched, verified data added directly to each team's entry in `data/franchise_knowledge.json` (same pattern as the existing `draft_history` field), rendered in full (not season-scoped) since its volume is small.

**Tech Stack:** Python, `nba_api` (already a dependency), pytest, WebSearch for trade-history verification.

## Global Constraints

- Roster data covers all 30 teams × 11 seasons (2015-16 through 2025-26), fetched live via `nba_api` — not fabricated or hand-curated.
- Trade history is scoped to trades *notable enough to have shaped a roster or franchise trajectory* within the 2015-16–2025-26 window. Excluded: free agency signings, draft-day trades (already covered by `draft_history`), waiver moves, and minor/depth-piece/salary-dump trades.
- Every `trade_history` fact must be verified against a real source before being written — no entry added from memory alone.
- Roster context is limited to **one season per team per request** (not all 11 years) to keep LLM context focused. Trade history is included **in full** per team (small enough, like `draft_history` already is).
- `resolve_season(message, history)` always returns a valid season string — defaulting to the most recent season present in the data when nothing is mentioned anywhere in the message or history.

---

### Task 1: `fetch_team_rosters.py` — pull and verify real roster data

**Files:**
- Create: `fetch_team_rosters.py`
- Create: `data/team_rosters.json` (generated output, committed)

**Interfaces:**
- Produces: `data/team_rosters.json` — `{"_note": ..., "<TeamShortName>": {"<season>": [{"player": str, "position": str}, ...], ...}, ...}` for all 30 teams × the 11 tracked seasons.
- Consumes: `nba_api.stats.endpoints.commonteamroster.CommonTeamRoster`, `nba_api.stats.static.teams` (already in `requirements.txt`).

- [ ] **Step 1: Write `fetch_team_rosters.py`**

```python
import json
import os
import time

from nba_api.stats.endpoints import commonteamroster
from nba_api.stats.static import teams

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_OUTPUT_PATH = os.path.join(_DATA_DIR, "team_rosters.json")

_TRACKED_TEAMS = {
    "Spurs": "San Antonio Spurs",
    "Celtics": "Boston Celtics",
    "Nets": "Brooklyn Nets",
    "Kings": "Sacramento Kings",
    "Hawks": "Atlanta Hawks",
    "Hornets": "Charlotte Hornets",
    "Bulls": "Chicago Bulls",
    "Cavaliers": "Cleveland Cavaliers",
    "Mavericks": "Dallas Mavericks",
    "Nuggets": "Denver Nuggets",
    "Pistons": "Detroit Pistons",
    "Warriors": "Golden State Warriors",
    "Rockets": "Houston Rockets",
    "Pacers": "Indiana Pacers",
    "Clippers": "Los Angeles Clippers",
    "Lakers": "Los Angeles Lakers",
    "Grizzlies": "Memphis Grizzlies",
    "Heat": "Miami Heat",
    "Bucks": "Milwaukee Bucks",
    "Timberwolves": "Minnesota Timberwolves",
    "Pelicans": "New Orleans Pelicans",
    "Knicks": "New York Knicks",
    "Thunder": "Oklahoma City Thunder",
    "Magic": "Orlando Magic",
    "76ers": "Philadelphia 76ers",
    "Suns": "Phoenix Suns",
    "TrailBlazers": "Portland Trail Blazers",
    "Raptors": "Toronto Raptors",
    "Jazz": "Utah Jazz",
    "Wizards": "Washington Wizards",
}

_SEASONS = [
    "2015-16", "2016-17", "2017-18", "2018-19", "2019-20",
    "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26",
]

_REQUEST_DELAY_SECONDS = 0.6


def _team_id(full_name):
    matches = teams.find_teams_by_full_name(full_name)
    if not matches:
        raise ValueError(f"No team found for {full_name}")
    return matches[0]["id"]


def fetch_team_season_roster(team_id, season):
    df = commonteamroster.CommonTeamRoster(team_id=team_id, season=season, timeout=30).get_data_frames()[0]
    return [
        {"player": row["PLAYER"], "position": row["POSITION"]}
        for row in df[["PLAYER", "POSITION"]].to_dict("records")
    ]


def main():
    rosters = {
        "_note": "Live data pulled via nba_api (CommonTeamRoster), 2015-16 through 2025-26. Re-run fetch_team_rosters.py to refresh.",
    }
    for short_name, full_name in _TRACKED_TEAMS.items():
        team_id = _team_id(full_name)
        rosters[short_name] = {}
        for season in _SEASONS:
            print(f"Fetching {full_name} {season}...")
            try:
                rosters[short_name][season] = fetch_team_season_roster(team_id, season)
            except Exception as e:
                print(f"  FAILED {full_name} {season}: {e}")
            time.sleep(_REQUEST_DELAY_SECONDS)

    with open(_OUTPUT_PATH, "w") as f:
        json.dump(rosters, f, indent=2)
    print(f"Wrote {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

Run: `source .venv/bin/activate && python fetch_team_rosters.py`
Expected: prints one line per team-season (330 total), takes roughly 5-10 minutes given the
delay, ends with `Wrote .../data/team_rosters.json`. A handful of individual `FAILED` lines
are tolerable (the script skips and continues) — if more than a few fail, re-run once before
proceeding (transient stats.nba.com issues are common).

- [ ] **Step 3: Spot-check accuracy**

Confirm `data/team_rosters.json`'s `"Nets"."2015-16"` entry contains exactly these 15 players
(already verified against a live nba_api call during design): Shane Larkin, Chris McCullough,
Jarrett Jack, Sean Kilpatrick, Sergey Karasev, Brook Lopez, Henry Sims, Donald Sloan, Wayne
Ellington, Markel Brown, Rondae Hollis-Jefferson, Thaddeus Young, Willie Reed, Thomas
Robinson, Bojan Bogdanovic.

Then pick 2 more team-seasons of your choice from the generated file and cross-check them
against a public source (e.g. basketball-reference.com's team season roster pages, via
WebSearch/WebFetch) — confirm the player list is accurate (a handful of end-of-bench/two-way
player discrepancies are acceptable; a wholesale mismatch is not and means the fetch failed
silently and Step 2 needs to be re-run for that team).

- [ ] **Step 4: Commit**

```bash
git add fetch_team_rosters.py data/team_rosters.json
git commit -m "feat: add live-fetched team roster data, 2015-16 through 2025-26"
```

---

### Task 2: `rag.py` — season resolution + roster/trade rendering

**Files:**
- Modify: `rag.py`
- Modify: `tests/test_rag.py`

**Interfaces:**
- Consumes: `data/team_rosters.json` from Task 1.
- Produces: `resolve_season(message: str, history: list[dict]) -> str` — always returns a valid season key, defaulting to the most recent season in the data.
- Produces: `get_team_roster(team: str, season: str) -> list[dict] | None`.
- Produces: `retrieve_context(team: str | None, season: str) -> str` — signature grows from `retrieve_context(team)` to `retrieve_context(team, season)`.
- Produces: `_team_document(team: str, season: str) -> str` — gains a `Roster (<season>): ...` line (omitted if no roster data for that team/season) and a `Trade history: ...` line reading `KNOWLEDGE[team].get("trade_history", [])` (omitted if empty — real trade data doesn't land until Tasks 4-8, so this line is expected to be absent for every team until then).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_rag.py` (add `import rag` at the top alongside the existing `from rag import ...` line, needed for the monkeypatch tests):

```python
import rag
from rag import resolve_team, mentioned_teams, resolve_season, get_team_roster, retrieve_context


def test_resolve_season_from_current_message_season_key_format():
    assert resolve_season("Tell me about the 2015-16 Nets", []) == "2015-16"


def test_resolve_season_from_current_message_verbose_format():
    assert resolve_season("Tell me about the 2015-2016 Nets", []) == "2015-16"


def test_resolve_season_from_current_message_bare_year():
    assert resolve_season("Tell me about the Nets in 2018", []) == "2018-19"


def test_resolve_season_falls_back_to_history():
    history = [
        {"role": "user", "content": "Tell me about the Nets in 2015-16"},
        {"role": "assistant", "content": "That roster included Brook Lopez."},
    ]
    assert resolve_season("Who else was on that roster?", history) == "2015-16"


def test_resolve_season_defaults_to_latest_when_nothing_found():
    assert resolve_season("Tell me about the Nets", []) == "2025-26"


def test_resolve_season_ignores_out_of_range_year():
    assert resolve_season("Tell me about the Nets in 1998", []) == "2025-26"


def test_get_team_roster_returns_list_for_known_team_season():
    roster = get_team_roster("Nets", "2015-16")
    assert roster is not None
    assert any(p["player"] == "Shane Larkin" for p in roster)


def test_get_team_roster_returns_none_for_unknown_season():
    assert get_team_roster("Nets", "1998-99") is None


def test_retrieve_context_includes_roster_line_for_resolved_season():
    doc = retrieve_context("Nets", "2015-16")
    assert "Roster (2015-16):" in doc
    assert "Shane Larkin (G)" in doc


def test_retrieve_context_omits_roster_line_when_season_has_no_data():
    doc = retrieve_context("Nets", "1998-99")
    assert "Roster (" not in doc


def test_retrieve_context_omits_trade_history_line_when_absent():
    doc = retrieve_context("Spurs", "2015-16")
    assert "Trade history:" not in doc


def test_retrieve_context_includes_trade_history_line_when_present(monkeypatch):
    monkeypatch.setitem(rag.KNOWLEDGE["Spurs"], "trade_history", [
        {
            "season": "2018-19",
            "trade": "Traded Kawhi Leonard and Danny Green to Toronto for DeMar DeRozan, Jakob Poeltl, and a protected first-round pick",
            "outcome": "Reset the roster after Leonard's trade request rather than rebuilding from scratch.",
        }
    ])
    doc = retrieve_context("Spurs", "2015-16")
    assert (
        "Trade history: 2018-19 Traded Kawhi Leonard and Danny Green to Toronto for "
        "DeMar DeRozan, Jakob Poeltl, and a protected first-round pick -> Reset the roster "
        "after Leonard's trade request rather than rebuilding from scratch."
    ) in doc


def test_retrieve_context_returns_empty_string_for_unknown_team():
    assert retrieve_context("NotATeam", "2015-16") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rag.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_season'` (and similar for
`get_team_roster`), since none of these exist yet.

- [ ] **Step 3: Implement the changes**

In `rag.py`, add the `ROSTERS` load alongside the existing `KNOWLEDGE`/`RECORDS`/`LEADERS`
loads near the top of the file:

```python
with open(os.path.join(_DATA_DIR, "team_rosters.json")) as f:
    ROSTERS = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
```

Add season-detection helpers and `resolve_season` (place after `resolve_team`):

```python
_SEASON_KEY_RE = re.compile(r"\b(?:19|20)\d{2}-\d{2}\b")
_SEASON_VERBOSE_RE = re.compile(r"\b((?:19|20)\d{2})-((?:19|20)\d{2})\b")
_BARE_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")


def _all_seasons():
    return sorted(next(iter(ROSTERS.values())).keys()) if ROSTERS else []


def _detect_season(text):
    all_seasons = _all_seasons()

    match = _SEASON_KEY_RE.search(text)
    if match and match.group(0) in all_seasons:
        return match.group(0)

    match = _SEASON_VERBOSE_RE.search(text)
    if match:
        candidate = f"{match.group(1)}-{match.group(2)[2:]}"
        if candidate in all_seasons:
            return candidate

    match = _BARE_YEAR_RE.search(text)
    if match:
        year = int(match.group(1))
        candidate = f"{year}-{str(year + 1)[2:]}"
        if candidate in all_seasons:
            return candidate

    return None


def resolve_season(message, history):
    season = _detect_season(message)
    if season:
        return season
    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        season = _detect_season(turn.get("content", ""))
        if season:
            return season
    all_seasons = _all_seasons()
    return all_seasons[-1] if all_seasons else None
```

Add `get_team_roster` next to the existing `get_team_records`/`get_team_leaders`:

```python
def get_team_roster(team, season):
    return ROSTERS.get(team, {}).get(season)
```

Replace `_team_document` and `retrieve_context`:

```python
def _team_document(team, season):
    info = KNOWLEDGE[team]
    records = RECORDS.get(team, {})
    lines = [
        f"{info['full_name']} ({team})",
        f"Summary: {info['summary']}",
        f"Championships: {info['championships'] or 'None in this period'}",
        f"Front office continuity: {info['front_office_continuity']}",
        f"Continuity pattern: {info['continuity_pattern']}",
        "Coaches: " + "; ".join(f"{c['name']} ({c['tenure']}) - {c['note']}" for c in info["coaches"]),
        "Key draft history: " + "; ".join(
            f"{d['year']} {d['pick']}: {d['player']} -> {d['outcome']}" for d in info["draft_history"]
        ),
        "Win totals by season: " + ", ".join(f"{s}: {w}" for s, w in records.items()),
    ]

    roster = get_team_roster(team, season)
    if roster:
        lines.append(
            f"Roster ({season}): " + ", ".join(f"{p['player']} ({p['position']})" for p in roster)
        )

    trades = info.get("trade_history", [])
    if trades:
        lines.append(
            "Trade history: " + "; ".join(
                f"{t['season']} {t['trade']} -> {t['outcome']}" for t in trades
            )
        )

    return "\n".join(lines)


def retrieve_context(team, season):
    if team not in KNOWLEDGE:
        return ""
    return _team_document(team, season)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rag.py -v`
Expected: PASS (all tests, including the pre-existing ones from earlier work).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: all tests pass — `test_llm.py` and `test_server.py` are untouched by this task so
should be unaffected.

- [ ] **Step 6: Commit**

```bash
git add rag.py tests/test_rag.py
git commit -m "feat: add season resolution and roster/trade-history rendering to rag.py"
```

---

### Task 3: `llm.py` — wire season resolution into the prompt

**Files:**
- Modify: `llm.py`

**Interfaces:**
- Consumes: `resolve_season(message, history)` and `retrieve_context(team, season)` from Task 2.

- [ ] **Step 1: Update `answer_question`**

In `llm.py`, change the import line:

```python
from rag import resolve_team, resolve_season, retrieve_context
```

Replace `answer_question`:

```python
def answer_question(message, history=None):
    history = history or []
    team = resolve_team(message, history)
    season = resolve_season(message, history)
    context = retrieve_context(team, season)
    client = _get_client()
    response = client.invoke(build_messages(message, history, context))
    return response.content
```

- [ ] **Step 2: Run the full suite**

Run: `pytest -v`
Expected: all tests still pass. `answer_question` itself has no direct unit test (matches the
existing pattern — it requires a network client and is only exercised indirectly through
`server.py`'s mocked tests), so this step is regression-checking, not new coverage.

- [ ] **Step 3: Commit**

```bash
git add llm.py
git commit -m "feat: resolve season alongside team when building LLM context"
```

---

### Task 4: Trade history — batch 1 (Spurs, Celtics, Nets, Kings, Hawks, Hornets)

**Files:**
- Modify: `data/franchise_knowledge.json` (only the `Spurs`, `Celtics`, `Nets`, `Kings`,
  `Hawks`, `Hornets` entries — do not touch other teams)

**Interfaces:**
- Produces: a `"trade_history"` array added to each of these 6 teams' objects, in the exact
  shape `_team_document` (Task 2) already renders: `[{"season": "YYYY-YY", "trade": "...",
  "outcome": "..."}, ...]`.

This is a research task, not a code task — the exact trades cannot be listed here because
they must be verified against real sources during implementation, not invented from memory.
Follow this process for each of the 6 teams:

- [ ] **Step 1: Research notable trades for each team**

For each team, search for trades it made between the 2015-16 and 2025-26 seasons (inclusive)
that were notable enough to have meaningfully changed the roster or the franchise's
trajectory — star players, meaningful draft-pick packages, trades that triggered a rebuild or
a contention window. Exclude: free agency signings (no players traded away), draft-day trades
already captured in that team's existing `draft_history` array (check it first — don't
duplicate), waiver claims, and minor bench/salary-dump trades with no real impact.

Use WebSearch (and WebFetch on a specific source page if needed) to confirm each trade's
season, the players/picks that went each direction, and why it mattered — before writing it
down. Do not add a trade you can't confirm; if search results are inconsistent or unclear on
a detail, either dig further or leave that trade out rather than guess.

**Worked example** (already verified — use this exact entry for the Spurs, in this format):

```json
"trade_history": [
  {
    "season": "2018-19",
    "trade": "Traded Kawhi Leonard and Danny Green to Toronto for DeMar DeRozan, Jakob Poeltl, and a protected first-round pick",
    "outcome": "Reset the roster after Leonard's trade request rather than rebuilding from scratch, keeping the Spurs competitive instead of tanking."
  }
]
```
(There may be other notable Spurs trades in this window too — research and add them the same
way; this example just shows the required format and verification bar.)

- [ ] **Step 2: Add `trade_history` to each team's entry in `data/franchise_knowledge.json`**

Add the array as a new key in each team's object (alongside the existing `full_name`,
`summary`, `coaches`, `draft_history`, etc. — don't reorder or modify existing keys). A team
with zero qualifying trades in this window gets `"trade_history": []` — that's a legitimate
outcome, not a failure (Task 2's rendering already handles an empty list by omitting the
line).

- [ ] **Step 3: Validate the JSON and rendering**

Run: `python3 -c "import json; json.load(open('data/franchise_knowledge.json'))"` — must not
raise (confirms valid JSON).

Run: `source .venv/bin/activate && python3 -c "
import rag
for team in ['Spurs', 'Celtics', 'Nets', 'Kings', 'Hawks', 'Hornets']:
    doc = rag.retrieve_context(team, '2025-26')
    print(team, '->', 'Trade history:' in doc)
"`
Expected: prints `True` for every team that got at least one trade, `False` for any team you
gave `[]` — confirms the new data actually renders through `_team_document`.

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: all tests still pass (this task doesn't touch any tested code, only data — this
just confirms nothing was broken).

- [ ] **Step 5: Commit**

```bash
git add data/franchise_knowledge.json
git commit -m "feat: add verified trade history for Spurs, Celtics, Nets, Kings, Hawks, Hornets"
```

---

### Task 5: Trade history — batch 2 (Bulls, Cavaliers, Mavericks, Nuggets, Pistons, Warriors)

**Files:**
- Modify: `data/franchise_knowledge.json` (only these 6 teams' entries)

**Interfaces:** same as Task 4.

Follow the identical process from Task 4 Steps 1-5 (research, verify via WebSearch, add
`trade_history` in the same schema, validate JSON + rendering, run full suite, commit) for:
Bulls, Cavaliers, Mavericks, Nuggets, Pistons, Warriors.

- [ ] **Step 1: Research and add verified `trade_history` for all 6 teams in this batch**
- [ ] **Step 2: Validate JSON validity and confirm rendering via the same `rag.retrieve_context` check as Task 4 Step 3, scoped to this batch's 6 teams**
- [ ] **Step 3: Run the full test suite (`pytest -v`) — expect all passing**
- [ ] **Step 4: Commit**

```bash
git add data/franchise_knowledge.json
git commit -m "feat: add verified trade history for Bulls, Cavaliers, Mavericks, Nuggets, Pistons, Warriors"
```

---

### Task 6: Trade history — batch 3 (Rockets, Pacers, Clippers, Lakers, Grizzlies, Heat)

**Files:**
- Modify: `data/franchise_knowledge.json` (only these 6 teams' entries)

**Interfaces:** same as Task 4.

Follow the identical process from Task 4 for: Rockets, Pacers, Clippers, Lakers, Grizzlies,
Heat.

- [ ] **Step 1: Research and add verified `trade_history` for all 6 teams in this batch**
- [ ] **Step 2: Validate JSON validity and confirm rendering via the same `rag.retrieve_context` check as Task 4 Step 3, scoped to this batch's 6 teams**
- [ ] **Step 3: Run the full test suite (`pytest -v`) — expect all passing**
- [ ] **Step 4: Commit**

```bash
git add data/franchise_knowledge.json
git commit -m "feat: add verified trade history for Rockets, Pacers, Clippers, Lakers, Grizzlies, Heat"
```

---

### Task 7: Trade history — batch 4 (Bucks, Timberwolves, Pelicans, Knicks, Thunder, Magic)

**Files:**
- Modify: `data/franchise_knowledge.json` (only these 6 teams' entries)

**Interfaces:** same as Task 4.

Follow the identical process from Task 4 for: Bucks, Timberwolves, Pelicans, Knicks, Thunder,
Magic.

- [ ] **Step 1: Research and add verified `trade_history` for all 6 teams in this batch**
- [ ] **Step 2: Validate JSON validity and confirm rendering via the same `rag.retrieve_context` check as Task 4 Step 3, scoped to this batch's 6 teams**
- [ ] **Step 3: Run the full test suite (`pytest -v`) — expect all passing**
- [ ] **Step 4: Commit**

```bash
git add data/franchise_knowledge.json
git commit -m "feat: add verified trade history for Bucks, Timberwolves, Pelicans, Knicks, Thunder, Magic"
```

---

### Task 8: Trade history — batch 5 (76ers, Suns, TrailBlazers, Raptors, Jazz, Wizards)

**Files:**
- Modify: `data/franchise_knowledge.json` (only these 6 teams' entries)

**Interfaces:** same as Task 4.

Follow the identical process from Task 4 for: 76ers, Suns, TrailBlazers, Raptors, Jazz,
Wizards.

- [ ] **Step 1: Research and add verified `trade_history` for all 6 teams in this batch**
- [ ] **Step 2: Validate JSON validity and confirm rendering via the same `rag.retrieve_context` check as Task 4 Step 3, scoped to this batch's 6 teams**
- [ ] **Step 3: Run the full test suite (`pytest -v`) — expect all passing**
- [ ] **Step 4: Commit**

```bash
git add data/franchise_knowledge.json
git commit -m "feat: add verified trade history for 76ers, Suns, TrailBlazers, Raptors, Jazz, Wizards"
```

---

### Task 9: End-to-end verification

**Files:** none (manual verification only, exercising Tasks 1-8 together)

- [ ] **Step 1: Verify roster question for a specific season**

With the server running (`source .venv/bin/activate && python server.py`, `GROQ_API_KEY` set
in `.env`), ask: "Who was on the Nets roster in 2015-16?"
Expected: the answer lists real players from that roster (e.g. Brook Lopez, Thaddeus Young),
not a "I don't have that information" response.

- [ ] **Step 2: Verify season follow-up without repeating the team**

Ask a follow-up naming a different season for the same team, e.g. "What about their 2020-21
roster?"
Expected: the answer reflects the 2020-21 Nets roster, not 2015-16 — confirms
`resolve_season` correctly picks up the new season from the current message.

- [ ] **Step 3: Verify default-to-latest-season behavior**

Start a new conversation and ask: "Tell me about the Lakers roster" (no season mentioned).
Expected: the answer reflects the most recent season's roster (2025-26), not an arbitrary or
empty one.

- [ ] **Step 4: Verify trade history is grounded**

Ask: "What was the biggest trade the Spurs made?" (or similar, for any team with researched
trade data).
Expected: the answer describes a real, verified trade (matching what was written into
`data/franchise_knowledge.json`), with specifics (players, why it mattered) — not a vague or
invented answer.

- [ ] **Step 5: Run the full test suite one final time**

Run: `pytest -v`
Expected: all tests passing.

- [ ] **Step 6: Commit any fixes found during verification**

If Steps 1-4 surface a bug, fix it, re-run the relevant tests plus the manual check, then
commit. If no issues are found, skip this step — nothing to commit.
