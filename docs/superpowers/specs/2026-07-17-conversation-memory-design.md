# Conversation Memory & Chat Transcript

## Problem

The chatbot's `/api/chat` endpoint is fully stateless: each call passes only the current
message to the LLM, with no memory of prior turns. The frontend also overwrites the single
`chatbotOutput` element on every response, so there's no visible transcript. As a result the
app cannot handle follow-up questions — e.g. asking "what about their draft picks?" after
"tell me about the Spurs" has no way to know which team "their" refers to, and the previous
answer disappears from the screen.

## Goals

- Support natural follow-up questions that don't re-name the team.
- Show a scrolling chat transcript (both user and assistant turns), not just the latest answer.
- Keep the app stateless on the server — no session store, no database.

## Non-goals

- Persisting conversation history across page reloads (in-memory only, by design).
- Server-side session management.

## API contract change

`POST /api/chat` request body gains a `history` field:

```json
{
  "message": "<latest user text>",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

`history` contains prior turns only — it does not include the new `message`. Missing or
empty `history` is treated as `[]`, so older clients / first messages keep working.

Response shape is unchanged: `{ response, status, team, chart, leaders }`.

## Backend changes

### `llm.py`

`answer_question(message, history)`:
- Cap `history` to the last ~10 messages before building the prompt, to bound token usage
  and latency.
- Build the LangChain message list as: system prompt → each capped `history` turn (mapped to
  `("user", content)` / `("assistant", content)`) → a final user turn with
  `Context:\n{context}\n\nQuestion: {message}` (same context-stuffing format as today).

### `rag.py`

New `resolve_team(message, history)`:
- Returns `mentioned_teams(message)[0]` if the current message names a team.
- Otherwise walks `history` backward over `role == "user"` turns and returns the first team
  found via `mentioned_teams` on that turn's content.
- Returns `None` if no team is found in the message or history.

This replaces the direct `mentioned_teams(message)` call used today to pick the `team` for
the response, the RAG context, and the chart/leaders panels.

### `server.py`

`/api/chat` reads `history` from the request body (default `[]`), and passes it through to
`answer_question` and `resolve_team` alongside `message`.

## Frontend changes

### `app.js`

- Keep an in-memory `history` array (`{role, content}`), scoped to the page session — no
  `localStorage`, so a reload starts a fresh conversation.
- On send: immediately render a user bubble in the transcript, POST `{message, history}`.
- On success: render an assistant bubble, then push both the user and assistant turns into
  `history`.
- On failure: render an error bubble in the transcript, but do **not** push anything into
  `history` — a failed turn must not corrupt the context sent on the next request.
- Chart/leaders panels continue to update from `data.team` / `data.chart` / `data.leaders`
  on every successful response, unchanged from today.

### `index.html` / `style.css`

- Replace the single `chatbotOutput` overwrite target with a scrolling transcript container
  that appends message bubbles and auto-scrolls to the bottom.
- Minimal new CSS for user-vs-assistant bubble styling, reusing existing color/font variables.

## Error handling

- Missing/empty `history` from a client is treated as `[]`.
- A failed request never mutates the client-side `history` array (see above).
- History truncation (capping to last ~10 messages) is silent — no user-facing error.

## Testing

- Manual: ask about a team, then ask a follow-up that doesn't name a team; confirm the answer
  and chart/leaders stay on the correct team.
- Manual: trigger a request failure mid-conversation (e.g. stop the server) and confirm the
  transcript shows an error bubble, and that the next successful turn's context is unaffected
  (no corrupted/empty turn was added to history).
- Manual: hold a conversation past ~10 turns and confirm older turns drop off without
  crashing or breaking the response.
