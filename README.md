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

### Season simulator

Simulates the full 82-game 2026-27 regular season, every team from 0-0, for the real
rosters (baseline) and for any set of player moves (scenario). Games already played
this season only inform player and team strength; they're never locked in as results.

**Run it**

| Command | What it does |
|---|---|
| `python -m tradesim.simulate` | 2026-27 projection -> `reports/season_2026_27.csv` / `.md` |
| `python -m tradesim.scenario kawhi-leonard:TOR:CLE` | Scenario vs baseline -> `reports/scenario_<name>.csv` / `.md` |
| `python -m tradesim.ratings` | Refit player ratings (after any data refresh or `config/long_injuries.json` edit) |
| `python -m tradesim.game_model` | Refit the game model |
| `python -m tradesim.backtest_nov9` | Backtest 2021-22 to 2025-26 and fit sigma_t -> `reports/backtest_nov9.md` |

#### Method

1. **Player impact** (points per 100 possessions vs an average player; `tradesim/ratings.py`),
   Basketball-Reference BPM with every setting fitted on 2019-20 to 2025-26:
   - *Prior:* minutes-weighted BPM over the last 3 seasons (each older season counts half),
     pulled toward -2.5 as if he'd also played 300 minutes there, plus an age adjustment
     (+1.2 for 23 and under ... -0.4 for 34+).
   - *Rookies:* by draft slot, `-0.88 - 0.58 x ln(pick)` (#1 -0.9, #30 -2.8); undrafted -3.0.
   - *This season:* `impact = (K x prior + m x BPM_now) / (K + m)`, m = minutes so far,
     K = 898 minutes (about 1,900 possessions), from a fitted noise model (how far players
     move from their prior, tau = 1.3, vs BPM noise over m minutes).
   - *Uncertainty:* each player has an SE (1.3 for veterans, 1.9 for rookies before this
     season's games) that shrinks as his minutes grow.
2. **Team strength** = `sum(impact x minutes / 48) + team residual`. The residual (observed
   net rating minus the player sum, 2025-26 plus 2026-27 to date) carries over only 16%,
   so it's under 1 point for every team.
3. **Minutes and availability** (`tradesim/rotation.py`): minutes per game played (this
   season blended with last); a full-strength rotation keeps the real rotation and trims the
   deepest bench to 240. Each simulated season, every player gets a games-played rate drawn
   around his expected availability (history plus this season, 68% league average for
   rotation players), played out as one injury spell; while he's out his minutes go to his
   backups (same G/F/C position first, closest on the depth chart, max +10 each).
   `config/long_injuries.json` overrides availability for known 15+ game absences.
4. **Moves:** departing players' minutes form a pool that incoming players fill first; any
   extra comes from the lowest-impact same/adjacent-position players; leftovers go to the
   next players up. A mild diminishing-returns haircut applies to stacked top-3s (15% of
   their contribution above 10 points; a simplification, not fitted).
5. **Game model** (`tradesim/game_model.py`): `P(home win) = Phi((S_home - S_away + 2.00 -
   2.36 x b2b difference) / 12.61)`, fitted on all 8,289 games 2018-19 to 2024-25 with actual
   season net ratings (home edge 0 on neutral floors). Each game produces a margin, so point
   differential is available.
6. **Uncertainty per simulated season:** every player's impact drawn once from
   `N(rating, SE)`; a small team residual draw (1.41); and a shared, zero-sum team-season
   error `eps_team ~ N(0, sigma_t)` for what moves a whole team together. sigma_t = 2.5,
   fitted on the backtest (below).
7. **Season rules** (`tradesim/standings.py`): win %, then the NBA's two-team and multi-team
   tiebreakers (head-to-head, division winner, division and conference record, record vs
   playoff-eligible teams, point differential; random draw last); seeds 7-10 play the
   play-in. Playoff % = top 6 or won through the play-in.
8. **Runs and output:** 10,000 seeded seasons in chunks of 2,000 (about 220 MB). Baseline
   and scenario share every random draw, so changes are paired; the baseline is cached in
   `data/cache/` per input fingerprint, so a scenario takes about 2.4 s. Reports give avg
   wins, 10-90% range, playoff %, play-in %, #1 seed % and changes with Monte Carlo SEs plus
   an 80% range for the change in wins (how much the move's effect varies across seasons);
   teams in the move are flagged, plus any team whose change is beyond 2 SE and at least
   0.5 wins or 2 points of odds.

#### Data sources

Every raw file is listed with its source URL and as-of date in `data/raw/SOURCES.json`:
Basketball-Reference advanced stats 2018-19 to 2026-27 (user exports), preseason Vegas win
totals 2021-22 to 2025-26 (`data/vegas_win_totals.csv`, source URL per row), nba_api (game logs,
schedules, standings and divisions, draft history, team ratings, rosters and acquisition
dates, as-of-Nov-9 game logs for the backtest), the user's contracts and cap sheet, and
ESPN's injury page for `config/long_injuries.json`. A few user-supplied files have no
recorded URL and are marked so.

#### Validation results

**Backtest as of November 9, 2021-22 to 2025-26** (`reports/backtest_nov9.md`): for each
season, only what was known on Nov 9 (rosters and minutes from game logs to that date,
pre-season player ratings, team results to date), with the rating model, game model and
sigma_t fitted on the other seasons; full season simulated from 0-0 on the real schedule.

| Measure (150 team-seasons, held out) | Result |
|---|---|
| Win-total average error | 7.3 wins (guessing 41 for everyone: 10.1) |
| Slope of actual on predicted wins | 0.95 (1.0 = right spread) |
| Actual wins inside the 50% / 80% interval | 51% / 78% |
| Playoff-odds Brier score | 0.175 (base rate: 0.249) |
| Players inside their 50% / 80% rating interval | 47-55% / 76-86% by season (no SE scaling needed) |

**Model vs Vegas** (`data/vegas_win_totals.csv`: preseason totals 2021-22 to 2025-26 from
Basketball-Reference's preseason odds pages, which credit sportsoddshistory.com; each season
scaled to sum to 1,230; Vegas playoff odds come from running the totals through the same
season simulator). Blend = w x model + (1 - w) x Vegas, with w fitted leave-one-season-out.

| 150 team-seasons | Model (as of Nov 9) | Vegas (preseason) | Blend |
|---|---|---|---|
| Win-total average error | 7.26 | 7.10 | 7.12 |
| Win-total RMSE | 9.03 | 9.00 | 8.89 |
| Slope of actual on predicted | 0.95 (90%: 0.85-1.07) | 0.85 | 0.93 |
| Playoff Brier | 0.174 | 0.152 | 0.160 |

- Win totals: no real difference (model - Vegas average error, 90% interval -0.70 to +1.04,
  resampling whole seasons).
- Playoff odds: Vegas is better (model - Vegas Brier +0.008 to +0.034). Running the model's
  totals through the same converter gives the same Brier (0.175), so Vegas's edge is in its
  totals for teams near the playoff cut, not in the conversion.
- The blend (w = 0.27-0.63 by fold) ties Vegas on win totals and is worse on playoff odds
  (blend - Vegas Brier +0.002 to +0.016), so it doesn't beat each alone and Vegas totals are
  not used for 2026-27. (It does beat the model alone.)
- Slope stays at 0.95, interval includes 1.0: no shrink toward 41 (tracked by a test).
- Biggest 2025-26 misses vs Vegas (`reports/miss_breakdown_2025_26.md`): LAL and PHI (stars
  out at the start of the season are missing from the backtest's Nov 9 rosters, plus luck in
  close games), NYK (three starters far above their prior together), BKN (rookies far below
  their draft-slot prior), CHI (rating misses, injuries, mid-season trades).

Playoff-odds calibration (sigma_t chosen leave-one-season-out):

| Predicted | Teams | Avg predicted | Actual |
|---|---|---|---|
| 0-10% | 16 | 6% | 0% |
| 10-30% | 22 | 19% | 32% |
| 30-50% | 28 | 41% | 39% |
| 50-70% | 26 | 62% | 58% |
| 70-90% | 49 | 79% | 78% |
| 90-100% | 9 | 95% | 100% |

sigma_t (2.5) minimizes the ranked probability score of actual win totals over the five
seasons; chosen on 4 seasons it lands at 2.0-3.0 for every held-out season. Teams in the
same season aren't independent, so treat +/-3 points of coverage and +/-8-10 points per
calibration bucket as noise. Other checks: tiebreakers reproduce the NBA's official seeds
for every team in 2018-19 and 2021-22 to 2025-26; the game model picks 70% of 2025-26
winners (not used to fit); same seed gives identical output; minutes always total 240;
moving a player to his own team changes nothing; swapping near-equal players moves wins
by < 0.5.

#### Known limitations

- **Fit and chemistry:** players are added up; how they fit together (spacing, two
  ball-dominant guards, defensive schemes) isn't modelled beyond the mild diminishing-returns
  haircut and position buckets.
- **Coaching changes:** the team residual (coaching/system) stays with the team and is
  estimated from past results, so a new coach's effect isn't captured.
- **Mid-season trades:** the simulator plays every roster for the full season from 0-0;
  real teams change during the season.
- **Injury model is simple:** one random spell per player per season from his history, plus
  a hand-maintained list of known 15+ game absences; shorter known injuries are ignored;
  when several players are out their costs are simply added; fatigue is only the
  back-to-back penalty.
- BPM undervalues some defensive specialists (a few teams look better when one sits).
- The backtest uses pre-season player ratings (no early-season player BPM exists for past
  seasons) and builds Nov 9 rosters from players who had played by then, so stars out
  injured at the start are missing; both make it harder than the live 2026-27 setting.
- The 2026-27 schedule's 30 in-season-tournament games aren't set yet (filled with
  same-conference matchups); "playoff-eligible" in the tiebreakers is read as the top 10.
- The game spread (sigma) was fitted on season-average strengths, so it also contains a
  little night-to-night lineup variation the simulator adds separately (about 1%).

### Trade checker limitations

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
- **Roster rule:** each team must end a trade with 14-15 standard contracts (per the
  project spec). The Kings currently have 13, so any trade that doesn't add a player fails.
