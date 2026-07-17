# Conversation Memory & Chat Transcript Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the chatbot remember prior turns in a conversation so follow-up questions (including ones that don't re-name a team) get answered in context, and show a scrolling chat transcript instead of overwriting the single latest answer.

**Architecture:** The frontend keeps an in-memory `history` array of `{role, content}` turns and sends it with every `/api/chat` request. The backend threads `history` through to the LLM prompt (capped to the last 10 messages) and uses a new `resolve_team(message, history)` helper — checks the current message first, falls back to the last team mentioned in `history` — to drive RAG context lookup and the response's `team`/`chart`/`leaders` fields.

**Tech Stack:** Flask, langchain-groq, vanilla JS/HTML/CSS (no build tooling), pytest for backend tests.

## Global Constraints

- History is capped to the last 10 messages before being sent to the LLM (`llm.py`).
- No server-side session or database — conversation state lives only in the browser tab's memory, not `localStorage`. A page reload starts a fresh conversation.
- Missing or empty `history` in a request is treated as `[]` (backward compatible with old clients).
- A failed `/api/chat` request must never be added to the client-side `history` array.
- `resolve_team(message, history)` is the single source of truth for which team drives RAG context, and the response's `team`/`chart`/`leaders` fields.

---

### Task 1: `rag.py` — team resolution across turns

**Files:**
- Modify: `rag.py`
- Create: `requirements-dev.txt`
- Create: `tests/test_rag.py`

**Interfaces:**
- Produces: `resolve_team(message: str, history: list[dict]) -> str | None` — `history` is a list of `{"role": "user"|"assistant", "content": str}` dicts. Returns the first team mentioned in `message`, else the most recent team mentioned in a `"user"` turn of `history` (walking backward), else `None`.
- Produces: `retrieve_context(team: str | None) -> str` — replaces the old `retrieve_context(query, k=3)`. Returns `""` if `team` is `None` or not in `KNOWLEDGE`, else `_team_document(team)`.
- Consumes: existing `mentioned_teams(query: str) -> list[str]` and `_team_document(team: str) -> str` (unchanged, already in `rag.py`).

- [ ] **Step 1: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest
```

- [ ] **Step 2: Install dev dependencies**

Run: `pip install -r requirements-dev.txt`
Expected: pytest installs successfully alongside the existing deps.

- [ ] **Step 3: Write the failing tests**

Create `tests/test_rag.py`:

```python
from rag import resolve_team


def test_resolve_team_from_current_message():
    assert resolve_team("Tell me about the Spurs", []) == "Spurs"


def test_resolve_team_falls_back_to_history():
    history = [
        {"role": "user", "content": "Tell me about the Spurs"},
        {"role": "assistant", "content": "The Spurs have had great continuity."},
    ]
    assert resolve_team("What about their draft picks?", history) == "Spurs"


def test_resolve_team_prefers_current_message_over_history():
    history = [
        {"role": "user", "content": "Tell me about the Spurs"},
        {"role": "assistant", "content": "The Spurs have had great continuity."},
    ]
    assert resolve_team("What about the Celtics?", history) == "Celtics"


def test_resolve_team_ignores_assistant_turns_when_falling_back():
    history = [
        {"role": "user", "content": "What makes a great coach?"},
        {"role": "assistant", "content": "The Spurs' Gregg Popovich is a great example."},
    ]
    assert resolve_team("Tell me more", history) is None


def test_resolve_team_returns_none_when_nothing_found():
    assert resolve_team("What makes a great coach?", []) is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_rag.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_team' from 'rag'`

- [ ] **Step 5: Implement `resolve_team` and refactor `retrieve_context`**

In `rag.py`, add `resolve_team` after `mentioned_teams`, and replace the existing `retrieve_context`:

```python
def resolve_team(message, history):
    teams = mentioned_teams(message)
    if teams:
        return teams[0]
    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        prior_teams = mentioned_teams(turn.get("content", ""))
        if prior_teams:
            return prior_teams[0]
    return None
```

Replace:

```python
def retrieve_context(query, k=3):
    teams = [t for t in mentioned_teams(query) if t in KNOWLEDGE][:k]
    if not teams:
        return ""
    return "\n\n".join(_team_document(team) for team in teams)
```

with:

```python
def retrieve_context(team):
    if team not in KNOWLEDGE:
        return ""
    return _team_document(team)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_rag.py -v`
Expected: PASS (5 passed)

- [ ] **Step 7: Commit**

```bash
git add rag.py requirements-dev.txt tests/test_rag.py
git commit -m "feat: add resolve_team for cross-turn team resolution"
```

---

### Task 2: `llm.py` — thread conversation history into the prompt

**Files:**
- Modify: `llm.py`
- Create: `tests/test_llm.py`

**Interfaces:**
- Consumes: `resolve_team(message, history)` and `retrieve_context(team)` from Task 1.
- Produces: `build_messages(message: str, history: list[dict], context: str) -> list[tuple[str, str]]` — pure function, no network calls. Returns `[("system", SYSTEM_PROMPT), *history_turns, ("user", "Context:\n{context}\n\nQuestion: {message}")]`, with `history` capped to the last 10 entries and each turn mapped to `("assistant", content)` if `role == "assistant"` else `("user", content)`.
- Produces: `answer_question(message: str, history: list[dict] | None = None) -> str` — now accepts `history`, defaults to `[]` when omitted.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_llm.py`:

```python
from llm import SYSTEM_PROMPT, build_messages


def test_build_messages_includes_system_prompt_first():
    messages = build_messages("Tell me about the Spurs", [], "Spurs context")
    assert messages[0] == ("system", SYSTEM_PROMPT)


def test_build_messages_includes_history_in_order():
    history = [
        {"role": "user", "content": "Tell me about the Spurs"},
        {"role": "assistant", "content": "They have great continuity."},
    ]
    messages = build_messages("What about their draft picks?", history, "Spurs context")
    assert messages[1] == ("user", "Tell me about the Spurs")
    assert messages[2] == ("assistant", "They have great continuity.")
    assert messages[-1] == (
        "user",
        "Context:\nSpurs context\n\nQuestion: What about their draft picks?",
    )


def test_build_messages_caps_history_to_last_ten():
    history = [{"role": "user", "content": f"msg {i}"} for i in range(15)]
    messages = build_messages("latest", history, "")
    # system + 10 capped history turns + final question = 12
    assert len(messages) == 12
    assert messages[1] == ("user", "msg 5")
    assert messages[-2] == ("user", "msg 14")


def test_build_messages_handles_empty_history():
    messages = build_messages("Tell me about the Spurs", [], "Spurs context")
    assert len(messages) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_messages' from 'llm'`

- [ ] **Step 3: Implement `build_messages` and refactor `answer_question`**

Replace the full contents of `llm.py`:

```python
import os

from langchain_groq import ChatGroq
from rag import resolve_team, retrieve_context

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
    context = retrieve_context(team)
    client = _get_client()
    response = client.invoke(build_messages(message, history, context))
    return response.content
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add llm.py tests/test_llm.py
git commit -m "feat: thread conversation history into the LLM prompt"
```

---

### Task 3: `server.py` — accept and forward `history`

**Files:**
- Modify: `server.py`
- Create: `tests/test_server.py`

**Interfaces:**
- Consumes: `answer_question(message, history)` from Task 2, `resolve_team(message, history)` and `get_team_records`/`get_team_leaders` from Task 1 / existing `rag.py`.
- Produces: `/api/chat` now reads an optional `history` field (list of `{role, content}` dicts, default `[]`) from the JSON body alongside `message`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_server.py`:

```python
from unittest.mock import patch

import server


def test_chat_endpoint_passes_history_to_answer_question():
    client = server.app.test_client()
    history = [{"role": "user", "content": "Tell me about the Spurs"}]

    with patch("server.answer_question", return_value="mocked answer") as mock_answer:
        response = client.post(
            "/api/chat",
            json={"message": "What about their draft picks?", "history": history},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["response"] == "mocked answer"
    assert data["team"] == "Spurs"
    mock_answer.assert_called_once_with("What about their draft picks?", history)


def test_chat_endpoint_defaults_history_to_empty_list():
    client = server.app.test_client()

    with patch("server.answer_question", return_value="mocked answer") as mock_answer:
        response = client.post("/api/chat", json={"message": "Tell me about the Celtics"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["team"] == "Celtics"
    mock_answer.assert_called_once_with("Tell me about the Celtics", [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v`
Expected: FAIL — `mock_answer.assert_called_once_with(...)` fails because `answer_question` is currently called with only `message`, and `resolve_team` isn't used yet for `team`.

- [ ] **Step 3: Update `/api/chat`**

Replace the full contents of `server.py`:

```python
import os
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

load_dotenv()

from llm import answer_question
from rag import get_team_leaders, get_team_records, resolve_team

app = Flask(__name__)
CORS(app)


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'No message provided'}), 400

        message = data['message']
        history = data.get('history') or []
        bot_response = answer_question(message, history)

        team = resolve_team(message, history)

        return jsonify({
            'response': bot_response,
            'status': 'success',
            'team': team,
            'chart': get_team_records(team) if team else None,
            'leaders': get_team_leaders(team) if team else None,
        })

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return jsonify({
            'error': 'Sorry, I encountered an error processing your request.',
            'status': 'error'
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest -v`
Expected: All tests from Tasks 1-3 pass (11 passed).

- [ ] **Step 6: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat: accept and forward conversation history in /api/chat"
```

---

### Task 4: Frontend — conversation history + scrolling transcript

**Files:**
- Modify: `static/app.js`
- Modify: `static/index.html`
- Modify: `static/style.css`

**Interfaces:**
- Consumes: `/api/chat` now accepts `{message, history}` and returns the same `{response, status, team, chart, leaders}` shape as before (Task 3).
- Consumes: existing `renderWinChart(team, records)` and `renderLeaders(team, leaders)` from `static/chart.js` (unchanged).

- [ ] **Step 1: Replace `static/app.js`**

```javascript
const screen1 = document.getElementById('screen1');
const screen2 = document.getElementById('screen2');
const chatbotOutput = document.getElementById('chatbotOutput');

let history = [];

function wireInput(inputId, buttonId) {
    const input = document.getElementById(inputId);
    const button = document.getElementById(buttonId);
    const handler = (event) => {
        if ((event.keyCode && event.keyCode === 13) || event.type === 'click') {
            const value = input.value.trim();
            if (value) {
                askChatBot(value);
                input.value = '';
            }
        }
    };
    button.onclick = handler;
    input.onkeyup = handler;
}

wireInput('chatbotInput', 'submitButton');
wireInput('chatbotInput2', 'submitButton2');

function appendMessage(className, text) {
    const bubble = document.createElement('div');
    bubble.className = `chat-message ${className}`;
    bubble.innerText = text;
    chatbotOutput.appendChild(bubble);
    chatbotOutput.scrollTop = chatbotOutput.scrollHeight;
    return bubble;
}

function askChatBot(userInput) {
    screen1.classList.add('hidden');
    screen2.classList.remove('hidden');
    appendMessage('user', userInput);
    const thinkingBubble = appendMessage('assistant thinking', 'thinking...');

    const requestHistory = history;

    const myRequest = new Request('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: userInput, history: requestHistory })
    });

    fetch(myRequest)
        .then(function(response) {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(function(data) {
            if (data.status === 'success') {
                thinkingBubble.className = 'chat-message assistant';
                thinkingBubble.innerText = data.response;
                history = requestHistory.concat(
                    { role: 'user', content: userInput },
                    { role: 'assistant', content: data.response }
                );
                renderWinChart(data.team, data.chart);
                renderLeaders(data.team, data.leaders);
            } else {
                thinkingBubble.className = 'chat-message error';
                thinkingBubble.innerText = data.error || 'Sorry, something went wrong.';
            }
        })
        .catch((err) => {
            console.error('Error:', err);
            thinkingBubble.className = 'chat-message error';
            thinkingBubble.innerText = 'Sorry, I\'m having trouble connecting. Please try again.';
        });
}
```

- [ ] **Step 2: Verify `static/index.html` needs no structural change**

`index.html` already has `<div id="chatbotOutput" class="chatbotOutput"></div>` inside `.chat-container` (around line 37) — `app.js` now appends bubble `<div>`s into it instead of setting `.innerText`, so no HTML edit is required. Confirm this by reading the file; skip to Step 3 if the container is already there unchanged.

- [ ] **Step 3: Add chat bubble styles to `static/style.css`**

Replace the existing `.chatbotOutput` rule (around line 68-78):

```css
.chatbotOutput {
    background: #f8f9fb;
    border-radius: 16px;
    padding: 22px 26px;
    font-size: 1.1rem;
    line-height: 1.6;
    color: #2d2d3a;
    border-left: 4px solid #667eea;
    min-height: 120px;
    max-height: 420px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 14px;
}

.chat-message {
    max-width: 85%;
    padding: 12px 16px;
    border-radius: 14px;
    line-height: 1.5;
    white-space: pre-wrap;
}

.chat-message.user {
    align-self: flex-end;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-bottom-right-radius: 4px;
}

.chat-message.assistant {
    align-self: flex-start;
    background: #eef0f6;
    color: #2d2d3a;
    border-bottom-left-radius: 4px;
}

.chat-message.assistant.thinking {
    color: #8a8fa3;
    font-style: italic;
}

.chat-message.error {
    align-self: flex-start;
    background: #fdeceb;
    color: #b3261e;
    border: 1px solid #f3c6c2;
}
```

In the `@media (max-width: 768px)` block (around line 199-209), update the `.chatbotOutput` line:

```css
    .chatbotOutput { padding: 18px 20px; font-size: 1rem; max-height: 320px; }
```

- [ ] **Step 4: Manually verify the transcript renders**

Run: `python server.py` (with `GROQ_API_KEY` set in `.env`), open `http://localhost:8080`.
- Ask a question. Confirm your message appears as a right-aligned bubble, an italic "thinking..." bubble appears, then gets replaced by the left-aligned answer bubble.
- Ask a second question. Confirm both prior bubbles remain visible above the new ones (scrolling transcript, not overwritten).

Expected: transcript accumulates messages top-to-bottom, auto-scrolls to the latest.

- [ ] **Step 5: Commit**

```bash
git add static/app.js static/style.css
git commit -m "feat: render a scrolling chat transcript and send conversation history"
```

---

### Task 5: End-to-end verification

**Files:** none (manual verification only, exercising Tasks 1-4 together)

- [ ] **Step 1: Verify follow-up without a team name**

With the server running, ask: "Does San Antonio need to address the power forward position to become a top-tier contender?" Then ask a follow-up that doesn't name a team, e.g. "What about their point guards?"
Expected: the second answer addresses the Spurs specifically (not a generic answer), and the chart/leaders panels still show Spurs data.

- [ ] **Step 2: Verify a correction is understood in context**

Ask about a team, get an answer that references a specific player, then reply with a correction like "<player> isn't on the roster anymore."
Expected: the bot's next answer acknowledges the correction in the context of the original question, instead of restarting from a generic answer as it did before this change.

- [ ] **Step 3: Verify a failed request doesn't corrupt history**

Stop the Flask server, send a message from the browser (request will fail), confirm an error bubble appears. Restart the server, send another message.
Expected: error bubble is shown and the app recovers cleanly on the next successful message — the browser console shows no errors from a malformed `history` array being sent.

- [ ] **Step 4: Verify history capping on a long conversation**

Send 12+ messages in one conversation.
Expected: no errors in the browser console or server logs; later answers still reflect the most recent few turns (older turns beyond the last 10 may no longer be remembered — this is expected).

- [ ] **Step 5: Commit any fixes found during verification**

If Steps 1-4 surface a bug, fix it, re-run the relevant automated tests (`pytest -v`) plus the manual check, then commit:

```bash
git add -A
git commit -m "fix: <describe the issue found during end-to-end verification>"
```

If no issues are found, skip this step — nothing to commit.
