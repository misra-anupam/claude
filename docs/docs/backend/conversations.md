# Conversations (Sidebar Backend)

`backend/app/conversations.py` + `backend/app/routers/conversations.py`

Powers the date-grouped conversation sidebar (see
[Frontend](../frontend.md#conversation-sidebar)). Two separate concerns,
deliberately split across two different storage mechanisms.

## Why a dedicated table, not the checkpointer's own schema

LangGraph's checkpointer stores conversation state keyed by `thread_id` in
its own `checkpoints`/`checkpoint_writes` tables. It would be possible to
query those directly for "which threads exist and when were they last
touched" -- but that schema is an **implementation detail** of
`langgraph-checkpoint-postgres`, not a public API, and could change across
versions. It also has no concept of a human-readable title.

Instead, a small dedicated table tracks just what the sidebar needs:

```sql
CREATE TABLE IF NOT EXISTS conversations (
    thread_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

```python
async def touch_conversation(dsn: str, thread_id: str, first_message: str) -> None:
    title = " ".join(first_message.split())[:60] or "New conversation"
    await conn.execute(
        """INSERT INTO conversations (thread_id, title, updated_at) VALUES (%s, %s, now())
           ON CONFLICT (thread_id) DO UPDATE SET updated_at = now()""",
        (thread_id, title),
    )
```

Called on **every** message (`routers/chat.py`, before streaming starts).
The `ON CONFLICT` clause only ever touches `updated_at` -- `title` is
written once, on the row's first insert, and never overwritten. Verified
live: a thread's title stayed exactly "What is 9 times 8?" after a second,
unrelated message bumped `updated_at` from `07:04:04` to `07:04:20`.

## History replay: reading real checkpoint state

`GET /api/conversations/{thread_id}/messages` reads directly from the
checkpointer (not the `conversations` table, which has no message content):

```python
async def get_conversation_messages(checkpointer, thread_id):
    tup = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
    messages = tup.checkpoint.get("channel_values", {}).get("messages", [])
    ...
```

Confirmed live against real stored checkpoints that `AIMessage.content` is
**not always a plain string** -- it can be a list of typed content blocks
(`{"type": "reasoning", ...}`, `{"type": "text", ...}`, tool-call blocks).
`_extract_text()` handles both shapes, pulling only `text`-type blocks:

```python
def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return str(content)
```

## Deliberate simplification: text-only replay

Tool calls and results are **excluded** from the replay view -- only
`HumanMessage` and the text portions of `AIMessage` are returned. Reopening
a past conversation shows the final text content as static bubbles, not a
re-animated tool-call sequence. This was a conscious choice (matches how
most chat apps show history), confirmed to produce sensible output even
for a tool-heavy conversation: a thread that generated a chart and a
diagram correctly replayed as two assistant text entries (the lead-in
"I'll generate both..." and the final summary), with no raw tool-call
JSON leaking into the view.

See [Roadmap](../roadmap.md) if full-fidelity replay (tool cards included)
is ever wanted.
