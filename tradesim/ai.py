"""The two LLM steps in trade suggestions, fenced in by code (Stage 5).

1. Needs: the LLM reads a team's numbers (no player names) and returns JSON with the
   positions and skills it needs. Only values from fixed lists are kept; a free-text
   summary is kept only if it names no player.
2. Explanations: 1-2 sentences per trade, from a facts sheet. Each one is checked: it may
   only name players in that trade, and every number in it must appear in the facts.
   Anything that fails falls back to a plain template sentence.

The LLM never names players from memory, decides legality, or picks trades: code does all
of that. Without GROQ_API_KEY (or if the call fails) the needs come from the data and the
explanations from the template; the result says which ("source": "ai" / "data" / "template").
"""
import json
import os
import re

from tradesim.names import name_key
from tradesim.skills import SKILLS

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

    def __init__(self, players):
        self.full = {}       # "nikola jokic" -> {ids}
        self.last = {}       # "jokic" -> {ids}
        self.names = {}
        for pid, p in players.items():
            key = name_key(p["name"])
            self.full.setdefault(key, set()).add(pid)
            self.last.setdefault(key.split()[-1], set()).add(pid)
            self.names[pid] = p["name"]

    def mentioned(self, text):
        """Player ids whose full name appears in the text, plus last names that appear on their
        own (after the full-name matches are blanked out, so "Derrick White" isn't also read as
        a bare "White")."""
        t = " " + name_key(text) + " "
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


def allowed_numbers(f):
    nums = [f["wins_before"], f["wins_after"], abs(f["win_change"]), f["playoff_before"], f["playoff_after"],
            abs(f["playoff_change"])]
    for p in f["gets"] + f["sends"]:
        nums += [abs(p["impact"]), p["salary_m"]]
    nums += [pk["year"] for pk in f.get("picks", [])]
    nums += list(range(0, 5))  # small counts ("two players", "1st round")
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
        allowed_ids = [p["id"] for p in f["gets"] + f["sends"]]
        ok = bool(text) and len(text) <= 400 and names_ok(text, allowed_ids, index) and numbers_ok(text, allowed_numbers(f))
        out.append({"text": text, "source": "ai"} if ok else {"text": templates[i], "source": "template",
                                                               "rejected": bool(text)})
    return out
