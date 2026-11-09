# NBA Franchise Analyst

An AI-powered NBA front-office analyst: a chat interface backed by team/player
stats, franchise history, and a basketball-fit trade evaluator, with
dashboards and comparison views alongside every answer.

## Setup

1. `pip install -r requirements.txt` (and `requirements-dev.txt` for tests).
2. Copy `.env.example` to `.env` and set `GROQ_API_KEY` (required). Optionally
   set `GROQ_MODEL` to override the default (`openai/gpt-oss-120b`).
3. `python server.py` (reads `PORT`, default `8080`).

Run the test suite with `pytest`.

## How it works

A question flows: `static/app.js` (composer) -> `POST /api/chat` ->
`rag.py`'s `build_context()` assembles a plain-text context string from the
data files below -> `llm.py`'s `answer_question()` sends that context plus
the system prompt to Groq -> the prose reply and resolved
team/player/season/comparison/trade flags come back together ->
`static/render/chatThread.js` renders the prose and, based on those flags
(not the LLM's own text), mounts an independently-fetched dashboard,
comparison, or leaders view (`/api/team/...`, `/api/player/...`,
`/api/leaders`).

## Data sources

| Data | Source | Freshness | Refresh |
|---|---|---|---|
| Team/player per-game & advanced stats, rosters, game logs, win totals | `nba_api` (stats.nba.com) | Live when fetched | `python fetch_*.py` (one script per dataset) |
| Championships, current head coach | `nba_api` (`TeamYearByYearStats.NBA_FINALS_APPEARANCE`, `CommonTeamRoster`'s coaches table), cross-checked against `FranchiseHistory.LEAGUE_TITLES` | Live when fetched | `python fetch_team_facts.py` |
| Franchise narrative (summary, continuity pattern, front-office continuity prose, historical coaching list, draft/trade history write-ups) | Hand-curated (`data/franchise_knowledge.json`) | Written once, not live | Manual edit |
| Player salaries (94 players, 28 of 30 teams) and league cap/tax/apron thresholds | A **partial, unverified** extract from HoopsHype's public pages, produced by ChatGPT on 2026-10-20 (`data/contracts.json`, `data/league_caps.json`) | One-time snapshot | Not automated — see Known limitations |
| LLM | Groq (`GROQ_MODEL`, default `openai/gpt-oss-120b`) via `langchain-groq` | N/A | N/A |

All `nba_api`-backed data covers the **2015-16 through 2025-26 seasons**
(2025-26 is "latest"). `data/player_leaders.json`, an older all-time
top-5-per-franchise seed file, is loaded at startup but no longer used by any
active code path — `rag.get_team_season_leaders()` computes real,
season-correct leaders from the live stats instead. It's kept around rather
than deleted; safe to remove.

## Known limitations

- **2026-27 is rosters only.** `data/team_rosters.json` includes 2026-27
  rosters (fetched 2026-11-09), but stats, leaders and dashboards stay on
  2025-26 as the latest season — the new season had too few games for
  meaningful stats. The season list comes from the stats files, so a roster
  season ahead of the stats doesn't become "latest". Every team's chat
  context includes its current (2026-27) roster; for 2026-27 stats the model
  says its stats end at 2025-26.
- **No front-office head (GM / president of basketball ops) data anywhere.**
  No live source exists for this, and nothing was hand-curated to avoid
  reintroducing the stale-data problem this app was built to fix. The model
  says plainly that it doesn't have this when asked.
- **Contracts/salary data is partial and unverified**, not a certified or
  complete source:
  - Only 94 of the league's ~450 players are covered, mostly each team's top
    earners — bench and minimum-salary players are almost never included.
  - Portland has no real salary data at all.
  - No years-remaining, option type (beyond what little HoopsHype exposes),
    guarantee status, no-trade clauses, or trade kickers.
  - No draft-pick or draft-pick-protection data exists anywhere in the app.
  - There is no live, legal, free API for any of this; rebuilding it would
    mean either a paid data vendor or further manual curation.
- **No real CBA/salary-cap-legality validation.** The trade evaluator is a
  basketball-fit assessment only. It can cite a known salary figure but is
  explicitly instructed never to declare a trade cap-feasible or
  salary-matching legal.
- **No injury data.**
- **LLM output isn't deterministic.** Prompt-level mitigations exist for
  known failure modes (labeled "Fact:"/"Judgment:" meta-commentary, flipped
  Yes/No polarity on negated hypothetical questions), including a
  post-processing regex backstop for leaked labels — but a language model can
  still occasionally get these wrong despite the mitigations.
- **No automated frontend tests.** All UI/CSS fixes (mobile layout, chart
  scaling, scroll behavior) were verified by reasoning about the code plus
  manual phone testing, not an automated test suite — there's no JS test
  runner in this project.
- **Minor, not-yet-addressed engineering items:** `requirements.txt` has no
  version pins (a fresh install could pull a breaking dependency update);
  CORS is wide open (`CORS(app)`, every origin allowed); there's no CI.

## Trade Simulator (in progress, `trade-simulator` branch)

Stage 1 adds the data layer and a cap-legality checker (`tradesim/`), with no UI yet.

- `python -m tradesim.build_data` turns the raw files in `data/raw/2026_27/`
  into `data/2026_27/league.json` and prints a report of anything it couldn't match.
- `config/cba_2026_27.json` holds every cap threshold and percentage, with sources.
- `tradesim/checker.py` returns pass / fail / not checked for each rule and team. No-trade clauses and one-year
  Bird veto rights count as a fail.

### Season simulator (Stage 2)

`python fetch_games.py` gets 2025-26 results and the 2026-27 schedule;
`python -m tradesim.fit` fits the win model; `python -m tradesim.backtest` runs the backtest.
Settings are in `config/sim.json`; fitted constants are saved to `data/model/fit.json`.

1. **Player value** (`tradesim/model.py`): Basketball-Reference BPM, blended with
   replacement level (-2.0) as if the player had also played 250 replacement minutes:
   `value = (BPM x MP + (-2.0) x 250) / (MP + 250)`.
   **Team strength** = sum of `(value - (-2.0)) x minutes / 48` over the roster. That is
   the team's expected net rating per 100 possessions plus a constant, which cancels out.
2. **Minutes:** expected minutes per game = 2025-26 minutes / max(games, 20). Players are
   sorted by that and each gets his minutes until the team's 240 are used. After a trade,
   the same rule runs on the new roster, so a departing player's minutes go to the next
   players in line. 2026 draft picks get default minutes by pick number.
3. **Win probability** (`tradesim/fit.py`): `P(home wins) = 1 / (1 + e^-(home + slope x
   (S_home - S_away)))`, fitted on all 1,230 games of 2025-26 (no home edge on neutral
   courts). Fit: home = 0.278 (even teams win 56.9% at home), slope = 0.130 per point.
4. **Season** (`tradesim/simulate.py`): each of the 1,230 games is a biased coin flip;
   5,000 seasons are drawn at once with numpy (about 0.1 s). Output: average wins, a
   10th-90th percentile range, the win distribution, and conference seed frequencies.
   Before/after comparisons reuse the same random numbers. Only teams in working trades
   change; draft picks don't affect the simulation.

**Backtest on 2025-26** (`data/model/backtest_2025_26.json`):

| Version | Average error | RMSE | Within 5 wins |
|---|---|---|---|
| Guess 41 wins for everyone | 11.6 wins | — | — |
| Actual minutes | 2.6 wins | 3.2 | 26/30 |
| Projected minutes (the rule used for trades) | 2.9 wins | 3.6 | 26/30 |

This is in-sample: 2025-26 stats predicting 2025-26 wins. It shows the pipeline turns
player stats into wins correctly, not how well it forecasts a new season.

### Limitations

- **Cap legality only.** The checker says whether a trade is allowed under the cap
  rules, not whether the other team would accept it.
- **Rules marked "not checked"** (the data needed isn't available):
  - Contract extensions and the poison-pill rule (no extension dates).
  - The Jan 15 restriction on players who re-signed with a raise over 20% (no raise data).
  - The 30-day wait for 2026 draft picks (no rookie signing dates).
  - Trade exceptions other than the 5 large ones in `trade_exceptions.txt`.
  - Cash sent earlier in the season (only this trade's cash is checked).
  - Outcomes of protected, swap and conditional picks (passed on as written), and
    Stepien Rule cases that depend on them.
- **Data caveats:**
  - Team salary (payroll + dead money) comes from the cap screenshot's apron columns,
    accurate to about ±$0.1M.
  - Hard caps from offseason moves come from a Hoops Rumors list dated July 10, 2026.
  - The Hornets' exception amount ($40,770,520) and date may be a copy error in the source file.
  - The one-year Bird veto list may be from last season.
  - Re-acquire checks only know each player's most recent move.
- **Simulator:**
  - No injuries or fatigue: every player is available for every game.
  - Simplified minutes: a fixed "next man up" rule, not real rotations or positions.
  - Players with no 2025-26 stats count as replacement level. That includes rookies and
    veterans who missed all of last season (e.g. Haliburton, Lillard, Irving, VanVleet),
    so their teams are likely underrated.
  - The win range reflects game-to-game luck only, not uncertainty about how good a
    team really is, so real outcomes vary more.
  - The 2026-27 schedule's last 2 games per team (in-season tournament) aren't set yet;
    they're filled with random same-conference matchups.
  - Playoff seeding breaks ties at random, not with the NBA's tiebreakers.
- **Roster rule:** each team must end a trade with 14-15 standard contracts (per the
  project spec). The Kings currently have 13, so any trade that doesn't add a player fails.
