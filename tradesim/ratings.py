"""Player impact ratings (points per 100 possessions vs an average player) and team residuals.

Everything here is fitted on Basketball-Reference BPM for 2018-19 to 2025-26; no
rating or constant is typed in by hand. Run `python -m tradesim.ratings` after any
data refresh: it fits the model, writes data/model/ratings_fit.json, and writes the
2026-27 ratings for every rostered player to data/model/player_ratings_2026_27.json.

1. Prior (what we expect before this season), for a player with history:
       raw   = (sum_k  r^(k-1) x MP_k x BPM_k  +  S x mu) / (sum_k r^(k-1) x MP_k  +  S)
       prior = raw + age_adjustment[age bucket]
   k = 1, 2, 3 seasons back; r = recency weight; S = shrinkage minutes; mu = what
   an unknown player is worth. r, S, mu and the age table are chosen to best predict
   the next season's BPM (minutes-weighted squared error) over 2019-20 to 2025-26.
   This is the "regression to the mean": a player is pulled toward mu by S minutes.

   Rookies: prior = a + b x ln(draft pick), fitted on 2018-2025 rookies.
   Undrafted players with no history: the average of such players.

2. Uncertainty and the current-season blend (empirical Bayes). For each player-season,
   the miss (BPM - prior) has variance  tau^2 + c / minutes:
     tau^2 = how much true ability moves away from the prior (doesn't shrink)
     c / m = noise in a BPM measured over m minutes (shrinks with minutes)
   Both are fitted from the misses binned by minutes. Then for 2026-27 to date:
       impact = (K x prior + m x BPM_now) / (K + m),   K = c / tau^2
       SE     = 1 / sqrt(1 / tau^2 + m / c)
   i.e. weight on this season = m / (m + K), as the spec asks (minutes stand in for
   possessions: about 2.1 possessions per minute).

3. Team residual = observed net rating - sum(player impact x minutes / 48).
   How much of it carries over to the next season (rho) is fitted on 2019-20 to
   2025-26; the 2026-27 residual is rho x (games-weighted 2025-26 and 2026-27 residual).
"""
import json
import math
import os
from functools import lru_cache

import numpy as np

from tradesim.history import CURRENT_SEASON, draft_history, load_season, previous, team_ratings
from tradesim.model import load_sim_config
from tradesim.names import name_key
from tradesim.teams import TEAM_INFO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIT_PATH = os.path.join(ROOT, "data", "model", "ratings_fit.json")
RATINGS_PATH = os.path.join(ROOT, "data", "model", "player_ratings_2026_27.json")


# --- inputs -----------------------------------------------------------------------------

@lru_cache(maxsize=None)
def draft_picks():
    """{name_key: (draft_year, pick)} (first time drafted)."""
    out = {}
    for p in sorted(draft_history(), key=lambda p: p["draft_year"]):
        out.setdefault(name_key(p["player"]), (p["draft_year"], p["pick"]))
    return out


def history(key, season, n):
    """[(seasons_back, record)] for the n seasons before `season` in which the player played."""
    out = []
    for k in range(1, n + 1):
        rec = load_season(previous(season, k))[0].get(key)
        if rec and rec.get("mp"):
            out.append((k, rec))
    return out


def age_bucket(age, buckets):
    for i, upper in enumerate(buckets):
        if age <= upper:
            return i
    return len(buckets)


def _target_age(hist, fallback=None):
    if hist:
        k, rec = hist[0]
        if rec.get("age"):
            return rec["age"] + k
    return fallback


def samples(cfg):
    """Every player-season used for fitting: target BPM/minutes plus history or draft slot."""
    rc = cfg["ratings"]
    out = []
    for season in rc["fit_target_seasons"]:
        totals, _ = load_season(season)
        for key, rec in totals.items():
            if not rec.get("mp") or rec["mp"] < rc["min_target_minutes"] or rec.get("bpm") is None:
                continue
            hist = history(key, season, rc["history_seasons"])
            draft = draft_picks().get(key)
            out.append({"key": key, "season": season, "bpm": rec["bpm"], "mp": rec["mp"], "g": rec["g"],
                        "age": rec.get("age") or _target_age(hist), "hist": hist,
                        "pick": draft[1] if draft and draft[0] <= int(season[:4]) else None})
    return out


# --- 1. prior ---------------------------------------------------------------------------

def raw_prior(hist, recency, shrink, mu):
    num, den = shrink * mu, shrink
    for k, rec in hist:
        w = recency ** (k - 1) * rec["mp"]
        num += w * rec["bpm"]
        den += w
    return num / den


def _fit_vets(vets, cfg):
    rc, grid = cfg["ratings"], cfg["ratings"]["grid"]
    y = np.array([s["bpm"] for s in vets])
    w = np.array([s["mp"] for s in vets], dtype=float)
    buckets = np.array([age_bucket(s["age"], rc["age_buckets"]) for s in vets])
    n_buckets = len(rc["age_buckets"]) + 1
    best = None
    for r in grid["recency"]:
        for shrink in grid["shrink_minutes"]:
            for mu in grid["prior_mean"]:
                raw = np.array([raw_prior(s["hist"], r, shrink, mu) for s in vets])
                resid = y - raw
                adj = np.array([np.average(resid[buckets == b], weights=w[buckets == b]) if (buckets == b).any() else 0.0
                                for b in range(n_buckets)])
                err = np.average((resid - adj[buckets]) ** 2, weights=w)
                if best is None or err < best[0]:
                    best = (err, r, shrink, mu, adj)
    err, r, shrink, mu, adj = best
    return {"recency": r, "shrink_minutes": shrink, "prior_mean": mu,
            "age_adjustment": [round(float(a), 3) for a in adj], "weighted_mse": round(float(err), 3)}


def _fit_rookies(rookies, undrafted):
    x = np.log([s["pick"] for s in rookies])
    y = np.array([s["bpm"] for s in rookies])
    w = np.array([s["mp"] for s in rookies], dtype=float)
    a_mat = np.column_stack([np.ones_like(x), x])
    b = np.linalg.solve(a_mat.T @ (a_mat * w[:, None]), a_mat.T @ (w * y))
    played = [s for s in rookies if s["g"] >= 10]
    xm = np.log([s["pick"] for s in played])
    ym = np.array([s["mp"] / s["g"] for s in played])
    m_mat = np.column_stack([np.ones_like(xm), xm])
    bm = np.linalg.lstsq(m_mat, ym, rcond=None)[0]
    und_w = np.array([s["mp"] for s in undrafted], dtype=float)
    und_mpg = [s["mp"] / s["g"] for s in undrafted if s["g"] >= 10]
    return {"bpm_intercept": round(float(b[0]), 3), "bpm_per_log_pick": round(float(b[1]), 3),
            "mpg_intercept": round(float(bm[0]), 2), "mpg_per_log_pick": round(float(bm[1]), 2),
            "undrafted_bpm": round(float(np.average([s["bpm"] for s in undrafted], weights=und_w)), 3),
            "undrafted_mpg": round(float(np.mean(und_mpg)), 2),
            "n_rookies": len(rookies), "n_undrafted": len(undrafted)}


def prior_for(hist, age, pick, fit, cfg):
    """(prior mean, prior SD) for one player from his history, age and draft slot."""
    rc = cfg["ratings"]
    if hist:
        v = fit["veterans"]
        raw = raw_prior(hist, v["recency"], v["shrink_minutes"], v["prior_mean"])
        bucket = age_bucket(age if age is not None else 27, rc["age_buckets"])
        return raw + v["age_adjustment"][bucket], fit["uncertainty"]["tau_veteran"]
    rk = fit["rookies"]
    if pick:
        return rk["bpm_intercept"] + rk["bpm_per_log_pick"] * math.log(pick), fit["uncertainty"]["tau_rookie"]
    return rk["undrafted_bpm"], fit["uncertainty"]["tau_rookie"]


# --- 2. uncertainty -----------------------------------------------------------------------

def _fit_noise(misses, n_bins=10):
    """Fit miss^2 = tau^2 + c / minutes on minutes-binned averages. Returns (tau^2, c)."""
    m = np.array([mp for mp, _ in misses], dtype=float)
    r2 = np.array([miss ** 2 for _, miss in misses])
    edges = np.quantile(m, np.linspace(0, 1, n_bins + 1))
    xs, ys = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (m >= lo) & (m <= hi)
        xs.append(np.mean(1 / m[sel]))
        ys.append(np.mean(r2[sel]))
    slope, intercept = np.polyfit(xs, ys, 1)
    return max(float(intercept), 0.25), max(float(slope), 1.0)


def posterior(prior, tau, bpm_now, minutes_now, c):
    """Blend the prior with this season's BPM. Returns (impact, SE)."""
    if not minutes_now or bpm_now is None:
        return prior, tau
    precision = 1 / tau ** 2 + minutes_now / c
    return (prior / tau ** 2 + bpm_now * minutes_now / c) / precision, 1 / math.sqrt(precision)


# --- 3. team residual -----------------------------------------------------------------------

def _impact_in_season(key, season, fit, cfg, totals_rec, age_fallback=None):
    hist = history(key, season, cfg["ratings"]["history_seasons"])
    draft = draft_picks().get(key)
    pick = draft[1] if draft and draft[0] <= int(season[:4]) else None
    prior, tau = prior_for(hist, (totals_rec or {}).get("age") or _target_age(hist, age_fallback), pick, fit, cfg)
    if not totals_rec:
        return prior, tau
    return posterior(prior, tau, totals_rec.get("bpm"), totals_rec.get("mp"), fit["uncertainty"]["c"])


def team_residuals(season, fit, cfg):
    """{team: observed net rating - player sum} for one season (players at their in-season impact)."""
    totals, stints = load_season(season)
    games = team_ratings()[season]
    sums = {code: 0.0 for code in TEAM_INFO}
    for s in stints:
        key = name_key(s["name"])
        impact, _ = _impact_in_season(key, season, fit, cfg, totals.get(key))
        sums[s["team"]] += impact * (s["mp"] or 0) / (games[s["team"]]["games"] * 48)
    return {code: games[code]["net_rating"] - sums[code] for code in TEAM_INFO}


def _fit_residual_persistence(fit, cfg):
    seasons = ["2018-19"] + cfg["ratings"]["fit_target_seasons"]
    resid = {s: team_residuals(s, fit, cfg) for s in seasons}
    x, y = [], []
    for a, b in zip(seasons[:-1], seasons[1:]):
        for code in TEAM_INFO:
            x.append(resid[a][code])
            y.append(resid[b][code])
    x, y = np.array(x), np.array(y)
    rho = float(np.clip(np.sum(x * y) / np.sum(x * x), 0, 1))
    return {"rho": round(rho, 3), "residual_sd": round(float(np.std(x)), 2),
            "by_season": {s: {c: round(v, 2) for c, v in r.items()} for s, r in resid.items()}}


# --- fit everything --------------------------------------------------------------------------

def fit(cfg=None, write=True):
    cfg = cfg or load_sim_config()
    data = samples(cfg)
    vets = [s for s in data if s["hist"]]
    rookies = [s for s in data if not s["hist"] and s["pick"]]
    undrafted = [s for s in data if not s["hist"] and not s["pick"]]
    result = {"veterans": _fit_vets(vets, cfg), "rookies": _fit_rookies(rookies, undrafted),
              "n_player_seasons": len(data), "fit_target_seasons": cfg["ratings"]["fit_target_seasons"]}
    # Noise model from veterans' misses, then the rookies' extra spread around the draft curve.
    vet_misses = []
    for s in vets:
        prior, _ = prior_for(s["hist"], s["age"], None, {**result, "uncertainty": {"tau_veteran": 0, "tau_rookie": 0}},
                             cfg)
        vet_misses.append((s["mp"], s["bpm"] - prior))
    tau2, c = _fit_noise(vet_misses)
    rk = result["rookies"]
    rookie_r2 = [(s["bpm"] - (rk["bpm_intercept"] + rk["bpm_per_log_pick"] * math.log(s["pick"]))) ** 2 - c / s["mp"]
                 for s in rookies]
    tau2_rookie = max(float(np.average(rookie_r2, weights=[s["mp"] for s in rookies])), tau2)
    result["uncertainty"] = {"tau_veteran": round(math.sqrt(tau2), 3), "tau_rookie": round(math.sqrt(tau2_rookie), 3),
                             "c": round(c, 1), "K_minutes": round(c / tau2), "K_possessions_approx": round(c / tau2 * 2.1)}
    result["team_residual"] = _fit_residual_persistence(result, cfg)
    result["availability"] = _fit_availability(cfg)
    if write:
        os.makedirs(os.path.dirname(FIT_PATH), exist_ok=True)
        with open(FIT_PATH, "w") as f:
            json.dump(result, f, indent=1)
    return result


def load_fit(path=FIT_PATH):
    with open(path) as f:
        return json.load(f)


# --- 2026-27 ratings for every rostered player ---------------------------------------------------

def rotation_minutes(mpgs, total, cap):
    """Turn expected minutes into a 240-minute rotation. Players keep their expected minutes
    (at most `cap`) in order, highest first; the deepest bench absorbs the excess. If the whole
    roster comes up short, everyone is scaled up. (Scaling everyone down proportionally was
    tried first: it cut stars' minutes as much as the bench's, e.g. Jokic 36 -> 28.)"""
    out, left = {}, total
    for k, v in sorted(mpgs.items(), key=lambda kv: (-kv[1], kv[0])):
        give = min(v, cap, left)
        out[k] = give
        left -= give
    if left > 1e-9:
        out = normalize_minutes(out, total, cap)
    return out


def normalize_minutes(mpgs, total, cap):
    """Scale expected minutes so they add up to `total`, with no player above `cap`."""
    out = dict(mpgs)
    for _ in range(50):
        free = {k: v for k, v in out.items() if v < cap}
        fixed = sum(v for k, v in out.items() if v >= cap)
        if not free or sum(free.values()) == 0:
            break
        scale = (total - fixed) / sum(free.values())
        out = {k: min(v * scale, cap) if k in free else cap for k, v in out.items()}
        if abs(sum(out.values()) - total) < 1e-9:
            break
    return out


@lru_cache(maxsize=None)
def season_games(season):
    """Average games per team in a season (82, but 72 in 2020-21, about 71 in 2019-20)."""
    games = [t["games"] for t in team_ratings()[season].values()]
    return sum(games) / len(games)


def availability(key, season, fit, cfg, games_now=None):
    """Expected share of team games a player plays: his games over the last two seasons (plus
    this season so far), shrunk toward the league average as if he'd also played
    `prior_games` games at the average rate. A season he missed entirely counts as 0 games
    if he was in the league the season before."""
    a = fit["availability"]
    played, possible = a["prior_games"] * a["mean"], a["prior_games"]
    recs = [load_season(previous(season, k))[0].get(key) for k in (1, 2, 3)]
    for k, rec in zip((1, 2), recs[:2]):
        if rec and rec.get("g"):
            played += rec["g"]
            possible += season_games(previous(season, k))
        elif any(recs[k:]):
            possible += season_games(previous(season, k))
    if games_now is not None:
        played += games_now
        possible += season_games(season)
    return min(played / possible, 1.0)


def _fit_availability(cfg):
    """League-average share of games played by rotation players (15+ minutes per game the
    season before), 2019-20 to 2025-26. Players who left the league (no games that season and
    none the next) are left out: that's retirement, not missed games."""
    shares = []
    seasons = cfg["ratings"]["fit_target_seasons"]
    for season in seasons:
        prev, now = load_season(previous(season))[0], load_season(season)[0]
        after = load_season(previous(season, -1))[0]
        for key, rec in prev.items():
            if not rec.get("g") or rec["mp"] / rec["g"] < 15:
                continue
            g = (now.get(key) or {}).get("g", 0)
            if g == 0 and key not in after:
                continue
            shares.append((min(g / season_games(season), 1.0), (key, season)))
    mean = float(np.mean([sh for sh, _ in shares]))
    # Spread of one player's season around his own expected share (not across players):
    # E[(share - p)^2] = p(1-p)/(kappa+1) for a Beta(kappa p, kappa (1-p)) season rate.
    provisional = {"availability": {"mean": mean, "prior_games": cfg["ratings"]["availability_prior_games"]}}
    sq, pq = [], []
    for share, (key, season) in shares:
        p_hat = availability(key, season, provisional, cfg)
        sq.append((share - p_hat) ** 2)
        pq.append(p_hat * (1 - p_hat))
    kappa = float(np.mean(pq) / np.mean(sq) - 1)
    return {"mean": round(mean, 3), "kappa": round(kappa, 2), "prior_games": cfg["ratings"]["availability_prior_games"],
            "n": len(shares)}


def prior_mpg(player_key, pick, fit, cfg, season=CURRENT_SEASON):
    """Expected minutes per game PLAYED before `season`: the last season he played, else the
    rookie curve by draft pick, else the undrafted average."""
    floor = cfg["minutes"]["games_floor"]
    for k in (1, 2):
        rec = load_season(previous(season, k))[0].get(player_key)
        if rec and rec.get("mp") and rec.get("g"):
            return rec["mp"] / max(rec["g"], floor)
    rk = fit["rookies"]
    if pick:
        return max(rk["mpg_intercept"] + rk["mpg_per_log_pick"] * math.log(pick), 4.0)
    return rk["undrafted_mpg"]


INJURIES_PATH = os.path.join(ROOT, "config", "long_injuries.json")
# The two in-season-tournament games not yet scheduled are played in mid-December; for
# counting games after a return date they're treated as on this date.
PLACEHOLDER_GAME_DATE = "2026-12-15"


def load_long_injuries(path=INJURIES_PATH):
    with open(path) as f:
        return json.load(f)


def games_after(team, from_date, schedule_games):
    """Team's games still to play on or after `from_date` (placeholders count as mid-December)."""
    n = 0
    for g in schedule_games:
        if team not in (g["home"], g["away"]) or str(g.get("status", "")).startswith("Final"):
            continue
        if (g.get("date") or PLACEHOLDER_GAME_DATE) >= from_date:
            n += 1
    return n


def injury_availability(entry, player, games_now, normal_availability, injuries, schedule_games):
    """Expected share of the 82 games a long-term-injured player plays this season:
    (games already played + games after his return x his normal availability) / 82.
    Raises if the absence is shorter than min_games_out."""
    team = player["team"]
    if entry["team"] != team:
        raise ValueError(f"long_injuries: {entry['player']} listed with {entry['team']}, but plays for {team}")
    remaining = games_after(team, injuries["as_of"], schedule_games)
    if "return_date" in entry:
        after_return = games_after(team, entry["return_date"], schedule_games)
    else:
        after_return = max(remaining - entry["games_out"], 0)
    games_out = remaining - after_return
    if games_out < injuries["min_games_out"]:
        raise ValueError(f"long_injuries: {entry['player']} is out {games_out} games; the file is for "
                         f"{injuries['min_games_out']}+ game absences")
    expected = games_now + after_return * normal_availability
    return min(max(expected / 82, 0.005), 1.0), {"games_out": games_out, "games_after_return": after_return,
                                                "expected_games_played": round(expected, 1)}


def build_ratings(league=None, fit_result=None, cfg=None, write=True):
    from tradesim.league import League
    cfg = cfg or load_sim_config()
    fit_result = fit_result or load_fit()
    league = league or League.load()
    rc = cfg["ratings"]
    now = load_season(CURRENT_SEASON)[0]
    injuries = load_long_injuries()
    injured = {e["player"]: e for e in injuries["injuries"]}
    unknown = set(injured) - set(league.players)
    if unknown:
        raise ValueError(f"long_injuries: unknown players {sorted(unknown)}")
    with open(os.path.join(ROOT, "data", "raw", "2026_27", "schedule.json")) as f:
        schedule_games = json.load(f)["games"]
    players = {}
    for pid, p in league.players.items():
        key = name_key(p["name"])
        hist = history(key, CURRENT_SEASON, rc["history_seasons"])
        acq = p.get("acquired", {})
        pick = acq.get("pick") if acq.get("type") == "draft" else None
        if pick is None:
            draft = draft_picks().get(key)
            pick = draft[1] if draft else None
        age = _target_age(hist, p.get("age"))
        prior, tau = prior_for(hist, age, pick, fit_result, cfg)
        cur = now.get(key) or {}
        impact, se = posterior(prior, tau, cur.get("bpm"), cur.get("mp"), fit_result["uncertainty"]["c"])
        mpg_before = prior_mpg(key, pick, fit_result, cfg)
        g_now = cur.get("g") or 0
        mpg_playing = ((cur.get("mp") or 0) + rc["minutes_prior_games"] * mpg_before) / (g_now + rc["minutes_prior_games"])
        avail = availability(key, CURRENT_SEASON, fit_result, cfg, games_now=g_now)
        long_injury = None
        if pid in injured:
            # Override (not on top): his normal availability from earlier seasons, applied only to
            # the games after his return; games he has already played count as played.
            normal = availability(key, CURRENT_SEASON, fit_result, cfg)
            avail, long_injury = injury_availability(injured[pid], p, g_now, normal, injuries, schedule_games)
            long_injury.update({"return_date": injured[pid].get("return_date"), "source_url": injured[pid]["source_url"]})
        players[pid] = {"name": p["name"], "team": p["team"], "age": age, "pick": pick,
                        "history_seasons": len(hist), "prior": round(prior, 3), "prior_se": round(tau, 3),
                        "bpm_2026_27": cur.get("bpm"), "minutes_2026_27": cur.get("mp"), "games_2026_27": g_now,
                        "impact": round(impact, 3), "se": round(se, 3),
                        "mpg_prior": round(mpg_before, 2), "mpg_when_playing": round(mpg_playing, 2),
                        "availability": round(avail, 3), "mpg_projected": round(mpg_playing * avail, 2),
                        "long_injury": long_injury}
    # Team residuals: 2025-26 (full season) and 2026-27 to date, weighted by games, times rho.
    rho = fit_result["team_residual"]["rho"]
    r25 = fit_result["team_residual"]["by_season"]["2025-26"]
    r26 = team_residuals(CURRENT_SEASON, fit_result, cfg)
    games = team_ratings()
    residuals = {}
    for code in TEAM_INFO:
        g25, g26 = games["2025-26"][code]["games"], games[CURRENT_SEASON][code]["games"]
        combined = (g25 * r25[code] + g26 * r26[code]) / (g25 + g26)
        residuals[code] = {"residual_2025_26": r25[code], "residual_2026_27": round(r26[code], 2),
                           "games_2026_27": g26, "residual": round(rho * combined, 3)}
    out = {"as_of": "2026-11-09", "players": players, "team_residuals": residuals,
           "long_injuries_as_of": injuries["as_of"],
           "long_injury_teams": sorted({players[pid]["team"] for pid in injured})}
    if write:
        with open(RATINGS_PATH, "w") as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
    return out


@lru_cache(maxsize=1)
def load_ratings(path=RATINGS_PATH):
    with open(path) as f:
        return json.load(f)


if __name__ == "__main__":
    f = fit()
    v, rk, u, tr = f["veterans"], f["rookies"], f["uncertainty"], f["team_residual"]
    print(f"Fitted on {f['n_player_seasons']} player-seasons ({', '.join(f['fit_target_seasons'])})")
    print(f"Prior: recency weight {v['recency']}, shrink {v['shrink_minutes']} min toward {v['prior_mean']}")
    print("Age adjustment (<=21, 22-23, 24-25, 26-27, 28-29, 30-31, 32-33, 34+):", v["age_adjustment"])
    print(f"Rookies: BPM = {rk['bpm_intercept']} + {rk['bpm_per_log_pick']} x ln(pick); "
          f"#1 pick {rk['bpm_intercept']:.1f}, #10 {rk['bpm_intercept'] + rk['bpm_per_log_pick'] * math.log(10):.1f}, "
          f"#30 {rk['bpm_intercept'] + rk['bpm_per_log_pick'] * math.log(30):.1f}; undrafted {rk['undrafted_bpm']}")
    print(f"Uncertainty: tau {u['tau_veteran']} (rookies {u['tau_rookie']}), noise c {u['c']}; "
          f"K = {u['K_minutes']} minutes (~{u['K_possessions_approx']} possessions)")
    print(f"Team residual carries over at rho = {tr['rho']} (spread {tr['residual_sd']})")
    print(f"Rotation players play {f['availability']['mean']:.0%} of games on average")
    r = build_ratings(fit_result=f)
    print(f"Wrote {FIT_PATH}\nWrote {RATINGS_PATH} ({len(r['players'])} players)")
