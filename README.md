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
