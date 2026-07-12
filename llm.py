import os

from langchain_groq import ChatGroq
from rag import retrieve_context

_GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

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


def answer_question(query):
    context = retrieve_context(query)
    client = _get_client()
    response = client.invoke([
        ("system", SYSTEM_PROMPT),
        ("user", f"Context:\n{context}\n\nQuestion: {query}"),
    ])
    return response.content
