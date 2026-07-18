# Team Roster & Trade History (2015-16 through 2025-26)

## Problem

The chatbot has no data on which players were on a team's roster in a given season, and no
data on the notable trades that shaped a roster over time. Asked "do you have the history of
teams' rosters from every year?", it correctly says no — the only per-player data in the app
is `player_leaders.json` (top 5 per stat category per franchise across the whole period), not
season-by-season rosters, and there's no structured trade data at all (only scattered
mentions inside existing prose fields like `continuity_pattern`). Users want to ask
roster-specific questions (e.g. "who was on the Nets in 2015-16?") and trade-specific
questions (e.g. "what trades reshaped the Nets' roster?") and get real answers grounded in
actual data.

## Goals

- Real, accurate roster data for all 30 teams across all 11 seasons (2015-16 through
  2025-26) — every player who appeared for the team that season, not a curated subset.
- Real, verified notable-trade history for all 30 teams across the same window — the trades
  that meaningfully changed a roster, not an exhaustive transaction log.
- The chatbot answers roster questions grounded in this data, for a specific season when
  one is mentioned (explicitly or via conversation history), defaulting to the most recent
  season otherwise.
- The chatbot answers trade questions grounded in real trade facts, for the team in scope.
- Keep per-request LLM context focused — one season's roster per team, not all 11 years
  dumped into every request. Trade history stays in full (it's small, like `draft_history`).

## Non-goals

- Mid-season transaction tracking (a player traded mid-season appears however
  `CommonTeamRoster` reports it — no attempt to reconcile multiple stints in one season).
- A dedicated roster or trade-history UI panel (chart/leaders panels are unaffected; this is
  a chat-context addition only).
- Historical roster/trade data before 2015-16 or new "notable players" curation — full
  roster, pulled live, matching the existing `fetch_nba_data.py` pattern for season records.
- An exhaustive trade transaction log (minor/depth-piece trades, salary-dump trades) — only
  trades notable enough to have shaped the roster or franchise trajectory.
- Free agency signings, draft-day trades already captured in `draft_history`, or waiver
  moves — `trade_history` is specifically player/pick-for-player/pick trades between teams.

## Data source & fetch script

New script `fetch_team_rosters.py`, sibling to the existing `fetch_nba_data.py` and following
the same structure (same `_TRACKED_TEAMS` mapping, same `_FIRST_SEASON`/`_LAST_SEASON`
constants). Uses `nba_api.stats.endpoints.commonteamroster.CommonTeamRoster(team_id, season)`
— confirmed reachable and fast (~0.4s/call) in this environment.

The full sweep is 30 teams × 11 seasons = 330 calls. Unlike `fetch_nba_data.py` (one call per
team), this script:
- Adds a short delay between calls (e.g. 0.6s) to stay polite to the unofficial endpoint.
- Wraps each individual call in a try/except that logs and skips on failure rather than
  aborting the whole run — losing one team-season shouldn't cost the other 329.

Output: `data/team_rosters.json`.

```json
{
  "_note": "Live data pulled via nba_api (CommonTeamRoster), 2015-16 through 2025-26. Re-run fetch_team_rosters.py to refresh.",
  "Nets": {
    "2015-16": [{"player": "Shane Larkin", "position": "G"}, {"player": "Brook Lopez", "position": "C"}, ...],
    "2016-17": [...]
  },
  ...
}
```

Any team-season that failed to fetch is simply absent from the output (not a null/empty
placeholder) — `get_team_roster` treats a missing entry the same as an empty roster.

After the script runs, a manual spot-check of a handful of team-seasons against a public
source (e.g. basketball-reference) happens before the generated `team_rosters.json` is
committed — same verification discipline used for `season_records.json` earlier in this
project.

## `rag.py` changes

### `resolve_season(message, history)`

Mirrors `resolve_team`'s shape:
1. Look for a season pattern in `message`, in this priority order:
   - `\b(19|20)\d{2}-\d{2}\b` — already in season-key format (e.g. "2015-16") → used as-is.
   - `\b(19|20)\d{2}-(19|20)\d{2}\b` — verbose form (e.g. "2015-2016") → collapsed to
     "2015-16".
   - `\b(19|20)\d{2}\b` — a bare year (e.g. "2018") → mapped to the season that starts that
     year, "2018-19".
   Only a match that lands on a season actually present in the data is accepted; anything
   else is treated as no match (so "1998" doesn't produce a nonsense season key).
2. If no match in `message`, walk `history` backward over `"user"` turns (same pattern as
   `resolve_team`) and apply the same detection to each, returning the first hit.
3. If nothing is found anywhere, return the most recent season present in the data (derived
   from the data itself — `max()` of the season keys — not a hardcoded string, so it doesn't
   need a code change every year).

### `get_team_roster(team, season)`

```python
def get_team_roster(team, season):
    return ROSTERS.get(team, {}).get(season)
```
Consistent with the existing `get_team_records`/`get_team_leaders` accessors.

### `_team_document(team, season)`

Gains a roster line for the resolved season only:

```
Roster (2015-16): Shane Larkin (G), Brook Lopez (C), Thaddeus Young (F), ...
```

If no roster data exists for that team/season (fetch failure or out-of-range season), the
line is omitted entirely rather than printed empty.

### `retrieve_context(team, season)`

Signature grows from `retrieve_context(team)` to `retrieve_context(team, season)`, threading
the resolved season into `_team_document`.

## Trade history: data source & storage

Unlike rosters, there's no clean API for trade transactions — `nba_api` wraps stats.nba.com's
stats endpoints (box scores, standings, rosters), not transaction history. Trade history is
hand-researched and verified the same way `franchise_knowledge.json`'s existing
`draft_history` and `continuity_pattern` fields already are (this file has no fetch script —
it's curated content, cross-checked against real sources, not generated).

Each of the 30 teams in `data/franchise_knowledge.json` gains a new `trade_history` array,
alongside the existing `draft_history`, scoped to trades that happened within the tracked
window (2015-16 through 2025-26 seasons) and notable enough to have mattered (star players,
meaningful draft-pick swaps, trades that reshaped a roster's trajectory) — not every minor
transaction. Same shape/spirit as `draft_history`:

```json
"trade_history": [
  {
    "season": "2019-20",
    "trade": "Traded Caris LeVert, Jarrett Allen, and a 2020 first-round pick to Cleveland for Kevin Durant... (illustrative — real entries verified per-team during implementation)",
    "outcome": "Short description of why this trade mattered to the franchise's trajectory."
  }
]
```

Given this spans all 30 teams, the research happens in batches during implementation (e.g.
delegated to a handful of research-focused subagents, each covering several teams), with each
fact checked via web search before being written into `franchise_knowledge.json` — the same
verification discipline already used to correct `season_records.json` earlier in this
project. No trade is added on the basis of memory alone.

## `rag.py` changes (trade history)

### `_team_document(team, season)`

Gains a trade-history line, using the team's full `trade_history` list (not season-scoped,
since the list is small — comparable in size to `draft_history`, not to the per-season
roster):

```
Trade history: 2019-20 Traded ... -> outcome; 2021-22 Traded ... -> outcome
```

If a team's `trade_history` is empty (no notable trades in the window), the line is omitted
entirely, same treatment as the roster line when data is missing.

No new accessor function is needed — `trade_history` is read directly off `KNOWLEDGE[team]`
inside `_team_document`, the same way `draft_history` already is.

## `llm.py` changes

`answer_question` resolves both `team = resolve_team(message, history)` and
`season = resolve_season(message, history)`, passing both into `retrieve_context(team, season)`.
(No separate resolution step needed for trades — they ride along with `team` inside
`_team_document`.)

## `server.py`

No change — `team`/`chart`/`leaders` response fields are unaffected; this feature only
changes what context the LLM sees, not the API response shape.

## Testing

- `resolve_season`: explicit season-key match, verbose "YYYY-YYYY" match, bare-year match,
  history fallback, default-to-latest-season, and an out-of-range year producing no match —
  all pure/no network, following the existing `test_rag.py` style.
- `_team_document`/`retrieve_context`: season-aware formatting includes the right season's
  roster line and omits it cleanly when no roster data exists for that team/season; trade
  history line includes all of a team's `trade_history` entries and omits the line cleanly
  when the list is empty.
- `fetch_team_rosters.py` itself is not unit-tested (I/O script hitting a live third-party
  API, same as `fetch_nba_data.py`) — verified instead by one manual run plus a spot-check
  of the generated data against a public source before committing it.
- Trade history data isn't unit-tested for factual accuracy (that's a research/verification
  step, not something a test can assert) — each entry is checked against a real source during
  research, same discipline as the `season_records.json` correction earlier in this project.
- Manual end-to-end: ask about a specific team+season roster, confirm the answer is grounded
  in the real data; ask a follow-up without repeating the season, confirm it still resolves
  from history; ask with no season mentioned at all, confirm it defaults to the most recent
  season's roster; ask about a team's notable trades, confirm the answer reflects real,
  verified trades rather than invented ones.
