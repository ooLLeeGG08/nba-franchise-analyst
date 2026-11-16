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

## What the chatbot is

The chatbot has two parts:

1. **A fact finder (plain Python, no AI).** `rag.py` reads your question and
   looks for team names, player names, seasons, and words like "trade" or
   "compare". It uses simple rules (text matching) to pull the matching facts
   from this app's data files: records, rosters, stat leaders, coaches,
   franchise history, and some salaries. No machine learning is used in this
   step.
2. **A writer (a neural network).** `llm.py` sends those facts to a large
   language model, `openai/gpt-oss-120b`, through the Groq API. It's a
   transformer neural network with about 120 billion parameters. It runs on
   Groq's servers, not inside this app. The model turns the facts into a
   readable answer.

This setup is called **RAG (retrieval-augmented generation)**: the app first
*retrieves* facts, then the model *generates* an answer from them. That way the
answer is based on this app's data, not on whatever the model happens to
remember from its training, which can be out of date.

### How a response is generated, step by step

1. **You ask a question**, for example "Why are the Spurs better than the
   Kings?"
2. **The app finds the topic.** It spots the teams (Spurs, Kings), any players,
   and the season. If you ask a follow-up like "what about their coach?", it
   looks back at your earlier messages to work out which team you mean.
3. **The app gathers the facts.** For each team or player it builds a short
   text summary from the data files. Trade questions also get the league's
   salary-cap rules. Every question gets a league-wide efficiency (PIE)
   leaderboard.
4. **The app picks the answer style.**
   - Normal question: a short plain answer (1-2 sentences for a simple fact).
   - Comparison or "why" question: one bold verdict and up to 3 bullet points.
   - Trade question: four parts: Verdict, Team fit, Risks, Bottom line.
5. **The app sends everything to the model.** That means the instructions
   (the "system prompt"), your last 10 messages, the facts, and your question.
   The instructions tell the model to:
   - use only the facts it was given
   - say "I don't have that data" instead of guessing
   - never claim a trade is cap-legal
   - remember that the data stops at the 2025-26 season
6. **The model writes the answer.** It predicts the reply one word piece at a
   time, using the facts and instructions it was given.
7. **The app cleans up and shows the answer.** It removes labels the model
   wasn't supposed to write (like "Fact:"). Then it shows the reply next to a
   team dashboard, player comparison, or leaders chart. Those charts come
   straight from the data, not from the model, so their numbers are always
   exact.

**Keep in mind:** the model can still make mistakes. It might misread a fact or
reason badly about a "what if" question. That's why the charts beside each
answer show the real numbers.

## How it works (technical)

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

- **No 2026-27 data.** The app was deliberately kept at "2025-26 is latest"
  rather than including the new season, which had too few games played for
  meaningful stats/leaders when this was built. If asked about 2026-27, the
  model is instructed to say its data ends at 2025-26.
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
