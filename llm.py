import os

from langchain_groq import ChatGroq
from rag import build_context

_GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
_MAX_HISTORY = 10

_client = None

SYSTEM_PROMPT = (
    "You are an NBA franchise-intelligence analyst. Answer questions about why some "
    "franchises (e.g. the Spurs, Celtics) sustain success and others (e.g. the Nets, Kings) "
    "struggle, using ONLY the factual context provided below plus general basketball "
    "reasoning. Cite specific facts from the context (coaches, draft picks, win totals, "
    "front-office continuity, player stat leaders, shooting/efficiency splits) to support your "
    "answer. The context may also include a two-player comparison block (PPG/APG/RPG/SPG plus "
    "TS%/USG%/PIE/OFF RTG/DEF RTG for each) and a league-wide PIE efficiency leaderboard -- use "
    "these to answer player-comparison and league-wide efficiency questions directly. PIE "
    "(Player Impact Estimate) is the NBA's own single-number impact stat, shown here in place of "
    "Basketball-Reference's PER, which isn't available from this data source -- say so if the "
    "user asks specifically about PER. Player stat leader (PPG/APG/RPG/SPG) figures are "
    "approximate seed data, not a live stats pull -- mention that if precision matters; the "
    "advanced stats (TS%/USG%/PIE/ratings) and PIE leaderboard ARE live pulled data, not "
    "approximations. If the context doesn't cover something, say so rather than inventing facts. "
    "Respond in plain conversational prose only: no "
    "markdown formatting, no tables, no bullet points, no headers, no bold/italic markers. "
    "Be concise: 3-5 sentences, covering only the 1-3 most important factors rather than "
    "exhaustively listing every fact in the context. Expand only if the user asks for more detail."
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
    context = build_context(message, history)
    client = _get_client()
    response = client.invoke(build_messages(message, history, context))
    return response.content
