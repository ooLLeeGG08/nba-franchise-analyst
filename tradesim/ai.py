"""The two LLM steps in trade suggestions, fenced in by code (Stage 5).

1. Needs: the LLM reads a team's numbers (no player names) and returns JSON with the
   positions and skills it needs. Only values from fixed lists are kept; a free-text
   summary is kept only if it names no player.
2. Explanations: 1-2 sentences per trade, from a facts sheet. Each one is checked (facts_ok):
   it may only name players in that trade; a number or team tied to a player must match
   league.json or the ratings file; other numbers must be facts of the trade. Names are
   matched without accents, suffixes or possessives ("Jokić's" = "Nikola Jokic").
   Anything that fails falls back to a plain template sentence.

The LLM never names players from memory, decides legality, or picks trades: code does all
of that. Without GROQ_API_KEY (or if the call fails) the needs come from the data and the
explanations from the template; the result says which ("source": "ai" / "data" / "template").
"""
import json
import os
import re

from tradesim.names import ALIASES, name_key
from tradesim.skills import SKILLS
from tradesim.teams import TEAM_INFO

POSITIONS = {"G": "Guards", "F": "Forwards", "C": "Centers"}
TIMELINES = ("contend", "retool", "rebuild")


def get_llm():
    """Groq chat model from the environment, or None if no key is set."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    from langchain_groq import ChatGroq
    return ChatGroq(model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"), api_key=key, temperature=0.2)


def ask_json(llm, system, user):
    """Call the model and parse the first JSON object in its reply."""
    reply = llm.invoke([("system", system), ("user", user)])
    text = getattr(reply, "content", reply)
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON in reply")
    return json.loads(match.group(0))


# --- names ---------------------------------------------------------------------------------------

class NameIndex:
    """Every player name in the database, for checking LLM text and resolving user input."""

    def __init__(self, players, ratings=None):
        self.full = {}       # "nikola jokic" -> {ids}
        self.last = {}       # "jokic" -> {ids}
        self.names = {}
        self.players = players          # league.json players: the source for teams and numbers
        self._ratings = ratings         # ratings file players (loaded on first use)
        for pid, p in players.items():
            key = name_key(p["name"])
            self.full.setdefault(key, set()).add(pid)
            self.last.setdefault(key.split()[-1], set()).add(pid)
            self.names[pid] = p["name"]
        for other, canonical in ALIASES.items():  # "Nic Claxton" names Nicolas Claxton too
            if canonical in self.full:
                self.full.setdefault(other, set()).update(self.full[canonical])

    @property
    def ratings(self):
        if self._ratings is None:
            from tradesim.ratings import load_ratings
            self._ratings = load_ratings()["players"]
        return self._ratings

    def mentioned(self, text):
        """Player ids whose full name appears in the text, plus last names that appear on their
        own (after the full-name matches are blanked out, so "Derrick White" isn't also read as
        a bare "White")."""
        t = " " + name_key(_drop_possessives(text)) + " "
        found_full = set()
        for key in sorted(self.full, key=len, reverse=True):  # longest names first
            if f" {key} " in t:
                found_full |= self.full[key]
                t = t.replace(f" {key} ", " | ")
        found_last = {last: ids for last, ids in self.last.items() if len(last) > 2 and f" {last} " in t}
        return found_full, found_last

    def resolve(self, query):
        """Turn a typed name into player ids: exact, ambiguous (ask the user to pick), or none."""
        key = name_key(query)
        if key in self.full:
            ids = sorted(self.full[key])
            return {"status": "exact" if len(ids) == 1 else "ambiguous", "candidates": ids}
        parts = key.split()
        ids = sorted({pid for k, s in self.full.items() if all(w in k.split() for w in parts) for pid in s}) if parts else []
        if len(ids) == 1:
            return {"status": "exact", "candidates": ids}
        return {"status": "ambiguous" if ids else "none", "candidates": ids[:10]}


def names_ok(text, allowed_ids, index):
    """True if the text names no player outside allowed_ids. Full names must be in the trade.
    A last name on its own is fine only if exactly one player in the trade has it (the trade
    makes it unambiguous); otherwise it could mean someone else, so the text is rejected."""
    allowed = set(allowed_ids)
    full, last = index.mentioned(text)
    if full - allowed:
        return False
    return all(len(ids & allowed) == 1 for ids in last.values())


def numbers_ok(text, allowed):
    """Every number written in the text must match an allowed number (to its shown precision)."""
    for raw in re.findall(r"\d+(?:\.\d+)?", text.replace(",", "")):
        value = float(raw)
        tol = 0.051 if "." in raw else 0.51
        if not any(abs(value - a) <= tol for a in allowed):
            return False
    return True


def _drop_possessives(text):
    """ "Jokić's" -> "Jokić" (otherwise it normalizes to "jokics" and matches nobody)."""
    return re.sub(r"(?<=[^\W\d_])['’]s?\b", "", text)


# Team names as normalized word sequences -> codes. Nicknames and cities count only when
# capitalized in the text ("the Heat", not "heat"); codes only in capitals ("WAS", not "was").
def _team_phrases():
    phrases = {}
    for code, info in TEAM_INFO.items():
        words = name_key(info["name"].replace("76ers", "Sixers")).split()
        nick = 2 if words[-2:] == ["trail", "blazers"] else 1
        for phrase in (words, words[-nick:], words[:-nick]):
            phrases.setdefault(tuple(phrase), set()).add(code)
    for extra, code in ((("blazers",), "POR"), (("sixers",), "PHI"), (("cavs",), "CLE"), (("wolves",), "MIN"),
                        (("mavs",), "DAL"), (("la",), "LAL"), (("la",), "LAC"), (("okc",), "OKC")):
        phrases.setdefault(extra, set()).add(code)
    return phrases


TEAM_PHRASES = _team_phrases()
_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?|[^\W\d_]+(?:[’'.\-][^\W\d_]+)*\.?")


def _tokens(sentence):
    """[(kind, value, capitalized)]: kind is "num" or "word" (normalized like player names)."""
    out = []
    for m in _TOKEN.finditer(_drop_possessives(sentence.replace("76ers", "Sixers"))):
        t = m.group(0)
        if t[0].isdigit():
            out.append(("num", t.replace(",", ""), False))
        elif t.rstrip(".") in TEAM_INFO:
            out.append(("team", {t.rstrip(".")}, True))
        else:
            for w in name_key(t).split():
                out.append(("word", w, t[0].isupper()))
    return out


def _mentions(tokens, index):
    """Player and team mentions in one sentence: [((start, end), "player"|"team", ids)].
    Full player names first (longest first), then team names, then lone last names."""
    words = [t[1] if t[0] == "word" else None for t in tokens]
    taken = [False] * len(tokens)
    found = []

    def scan(phrases, kind, need_cap=False):
        for phrase in sorted(phrases, key=len, reverse=True):
            n = len(phrase)
            for i in range(len(words) - n + 1):
                if any(taken[i:i + n]) or tuple(words[i:i + n]) != phrase:
                    continue
                if need_cap and not tokens[i][2]:
                    continue
                found.append(((i, i + n - 1), kind, set(phrases[phrase])))
                for j in range(i, i + n):
                    taken[j] = True

    scan({tuple(k.split()): v for k, v in index.full.items()}, "player")
    for i, t in enumerate(tokens):
        if t[0] == "team":
            found.append(((i, i), "team", t[1]))
            taken[i] = True
    scan(TEAM_PHRASES, "team", need_cap=True)
    scan({(k,): v for k, v in index.last.items() if len(k) > 2}, "player_last")
    return sorted(found, key=lambda x: x[0])


def _player_numbers(pid, index):
    """Every number league.json or the ratings file holds for a player (salary in $M, age,
    stats, impact, minutes, availability...), as written (fractions also x100)."""
    p, r = index.players.get(pid, {}), index.ratings.get(pid, {})
    values = []
    if p.get("salary"):
        values.append(p["salary"] / 1e6)
    for source in (p, p.get("stats_2025_26") or {}, p.get("stats_2024_25") or {}, r):
        for k, v in source.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k != "salary":
                values.append(abs(v))
                if 0 < abs(v) < 1:
                    values.append(abs(v) * 100)
    return values


def _close(raw, allowed):
    value, tol = float(raw), (0.051 if "." in raw else 0.51)
    return any(abs(value - a) <= tol for a in allowed)


def facts_ok(text, f, index):
    """The explanation check, sentence by sentence. Each number and team is tied to the
    player named just before it in the same sentence (or just after, if none is before):
      - a number must be a team-level fact (wins, playoff odds, changes, pick years, small
        counts) or one of THAT player's values in league.json or the ratings file;
      - a team must be that player's team in league.json or where this trade sends him.
    In a sentence naming no player, numbers must be facts of the trade and teams must be in it.
    Player names follow names_ok (only players in the trade; a lone last name must be unique
    among them). Returns (ok, reason)."""
    players = f["gets"] + f["sends"]
    allowed_ids = {p["id"] for p in players}
    teams_of = {p["id"]: {p.get("from"), p.get("to"), (index.players.get(p["id"]) or {}).get("team")} - {None}
                for p in players}
    trade_teams = {f["team"]} | set().union(*teams_of.values()) if teams_of else {f["team"]}
    team_level = team_numbers(f)
    any_player = team_level + [v for p in players for v in (abs(p["impact"]), p["salary_m"])]
    # sentence ends: ".!?" after a lowercase letter, digit, % or bracket and before a capital
    # (so "P.J. Washington" stays whole), or any ";"
    for sentence in re.split(r"(?<=[a-z0-9%)\]][.!?])\s+(?=[A-Z])|(?<=;)\s+", text):
        tokens = _tokens(sentence)
        mentions = _mentions(tokens, index)
        named = []  # (position, pid)
        for pos, kind, ids in mentions:
            if kind == "player":
                if len(ids) != 1 or not ids <= allowed_ids:
                    return False, f"names a player outside the trade: {sorted(ids)}"
                named.append((pos, next(iter(ids))))
            elif kind == "player_last":
                mine = ids & allowed_ids
                if len(mine) != 1:
                    return False, "a last name that could mean a player outside the trade"
                named.append((pos, next(iter(mine))))

        def nearest(i):
            """The player a number or team at token i is about: the last one named before it
            ("Josh Giddey (G, +1.4)", "White leaves Boston"), else the first one after it
            ("BOS sends White")."""
            before = [pid for (start, end), pid in named if end < i]
            after = [pid for (start, end), pid in named if start > i]
            return before[-1] if before else (after[0] if after else None)

        for pos, kind, ids in mentions:
            if kind != "team":
                continue
            pid = nearest(pos[0])
            ok_teams = teams_of[pid] if pid else trade_teams
            if not ids & ok_teams:
                return False, f"team {sorted(ids)} doesn't match {index.names.get(pid, 'the trade')}"
        for i, (kind, raw, _) in enumerate(tokens):
            if kind != "num":
                continue
            pid = nearest(i)
            allowed = team_level + _player_numbers(pid, index) if pid else any_player
            if not _close(raw, allowed):
                return False, f"number {raw} not in the data" + (f" for {index.names[pid]}" if pid else "")
    return True, None


# --- step 1: needs ----------------------------------------------------------------------------------

NEEDS_SYSTEM = (
    "You are an NBA front-office analyst. You get one team's numbers and return what it needs to "
    "become a contender, as JSON only: {\"timeline\": one of " + json.dumps(list(TIMELINES)) + ", "
    "\"positions\": 1-2 of [\"G\", \"F\", \"C\"] most needed first, \"skills\": 1-3 of "
    + json.dumps(list(SKILLS)) + ", \"summary\": one sentence}. Never name any player, real or "
    "otherwise, and do not suggest trades. Use only the numbers given."
)


def data_needs(facts):
    """Needs straight from the numbers (used without an LLM, or to fill gaps)."""
    positions = [g for g, name in POSITIONS.items() if name in facts["needs"]][:2] or ["F"]
    if facts.get("position_skills") and facts.get("league_position_skills"):
        # skills where the team's players at the most-needed position fall furthest behind the
        # league's players at that position (a center need -> e.g. rim protection, rebounding)
        team, league = facts["position_skills"][positions[0]], facts["league_position_skills"][positions[0]]
        skills = sorted(team, key=lambda sk: team[sk] - league[sk])[:2]
    else:
        skills = sorted(facts["team_skills"], key=lambda s: facts["team_skills"][s])[:2]
    p = facts["projection"]["playoff_pct"]
    timeline = "contend" if p >= 0.5 else ("retool" if p >= 0.2 else "rebuild")
    summary = (f"Weakest at {', '.join(POSITIONS[x].lower() for x in positions)}; lowest skills: "
               f"{' and '.join(skills)}.")
    return {"timeline": timeline, "positions": positions, "skills": skills, "summary": summary}


def team_needs(facts, index, llm=None):
    """Needs JSON from the LLM, validated; falls back to the data for anything invalid."""
    fallback = data_needs(facts)
    if llm is None:
        return {**fallback, "source": "data", "note": "AI analysis unavailable; needs come from the numbers."}
    user = json.dumps({k: v for k, v in facts.items() if k != "team_name"}, indent=1)
    try:
        raw = ask_json(llm, NEEDS_SYSTEM, user)
    except Exception as err:  # network, quota, bad JSON
        return {**fallback, "source": "data", "note": f"AI analysis failed ({type(err).__name__}); needs come from the numbers."}
    out, dropped = dict(fallback), []
    positions = [x for x in raw.get("positions", []) if x in POSITIONS][:2]
    skills = [x for x in raw.get("skills", []) if x in SKILLS][:3]
    out["positions"] = positions or fallback["positions"]
    out["skills"] = skills or fallback["skills"]
    out["timeline"] = raw.get("timeline") if raw.get("timeline") in TIMELINES else fallback["timeline"]
    summary = str(raw.get("summary", ""))[:240]
    if summary and names_ok(summary, [], index):
        out["summary"] = summary
    elif summary:
        dropped.append("summary named a player")
    if len(positions) != len(raw.get("positions", [])) or len(skills) != len(raw.get("skills", [])):
        dropped.append("values outside the allowed lists")
    return {**out, "source": "ai", "note": ("Checked: " + "; ".join(dropped) + " (replaced from the data).") if dropped else ""}


# --- step 2: explanations ------------------------------------------------------------------------------

EXPLAIN_SYSTEM = (
    "You explain NBA trade simulations to fans. For each trade you get a facts sheet. Write 1-2 "
    "plain sentences per trade saying why it helps the team, using ONLY the names and numbers in "
    "its facts sheet. Do not add any other player, number, statistic or opinion about fairness or "
    "whether the other team would agree. Reply as JSON: {\"explanations\": [\"...\", ...]} in the "
    "same order as the trades."
)


def template_explanation(f):
    gets = ", ".join(f"{p['name']} ({p['position']}, {p['impact']:+.1f})" for p in f["gets"])
    sends = ", ".join(p["name"] for p in f["sends"]) or "picks"
    return (f"{f['team']} adds {gets} for {sends}: projected wins {f['wins_before']:.1f} -> "
            f"{f['wins_after']:.1f} ({f['win_change']:+.1f}), playoff odds {f['playoff_before']:.0f}% -> "
            f"{f['playoff_after']:.0f}%.")


def team_numbers(f):
    """Numbers about the trade as a whole: wins, playoff odds, their changes, pick years, small
    counts ("two players", "1st round")."""
    nums = [f["wins_before"], f["wins_after"], abs(f["win_change"]), f["playoff_before"], f["playoff_after"],
            abs(f["playoff_change"])]
    nums += [pk["year"] for pk in f.get("picks", [])]
    nums += list(range(0, 5))
    return nums


def allowed_numbers(f):
    nums = team_numbers(f)
    for p in f["gets"] + f["sends"]:
        nums += [abs(p["impact"]), p["salary_m"]]
    return nums


def explain(trade_facts, index, llm=None):
    """One explanation per trade: the LLM's if it passes the name and number checks, else the template."""
    templates = [template_explanation(f) for f in trade_facts]
    if llm is None or not trade_facts:
        return [{"text": t, "source": "template"} for t in templates]
    try:
        raw = ask_json(llm, EXPLAIN_SYSTEM, json.dumps({"trades": trade_facts}, indent=1))
        texts = list(raw.get("explanations", []))
    except Exception:
        return [{"text": t, "source": "template"} for t in templates]
    out = []
    for i, f in enumerate(trade_facts):
        text = str(texts[i]).strip() if i < len(texts) else ""
        ok, reason = (facts_ok(text, f, index) if text and len(text) <= 400
                      else (False, "empty or too long" if not text or len(text) > 400 else None))
        out.append({"text": text, "source": "ai"} if ok else {"text": templates[i], "source": "template",
                                                               "rejected": bool(text), "reason": reason})
    return out
