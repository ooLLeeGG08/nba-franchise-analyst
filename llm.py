import os

from langchain_groq import ChatGroq
from rag import resolve_team, resolve_season, retrieve_context

_GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
_MAX_HISTORY = 10

_client = None

SYSTEM_PROMPT = (
    "You are an NBA franchise-intelligence analyst. Answer questions about why some "
    "franchises (e.g. the Spurs, Celtics) sustain success and others (e.g. the Nets, Kings) "
    "struggle, using ONLY the factual context provided below plus general basketball "
    "reasoning. Cite specific facts from the context (coaches, draft picks, win totals, "
    "front-office continuity) to support your answer. If the context doesn't cover something, "
    "say so rather than inventing facts."
)


def _get_client():
    global _client
    if _client is None:
        _client = ChatGroq(model=_GROQ_MODEL, api_key=os.environ["GROQ_API_KEY"])
    return _client


def build_messages(message, history, context):
    capped_history = history[-_MAX_HISTORY:] if history else []
    messages = [("system", SYSTEM_PROMPT)]
    for turn in capped_history:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        messages.append((role, turn.get("content", "")))
    messages.append(("user", f"Context:\n{context}\n\nQuestion: {message}"))
    return messages


def answer_question(message, history=None):
    history = history or []
    team = resolve_team(message, history)
    season = resolve_season(message, history)
    context = retrieve_context(team, season)
    client = _get_client()
    response = client.invoke(build_messages(message, history, context))
    return response.content
