# Long-Term Memory

`backend/app/tools/memory_tools.py`

```python
@tool
async def save_memory(fact: str) -> str: ...

@tool
async def search_memory(query: str) -> str: ...
```

## User-scoped, not thread-scoped

This is the key distinction from conversation history: per-thread
conversation state (what the checkpointer stores) resets at a new
`thread_id`. Long-term memory, stored via LangGraph's `BaseStore` under
namespace `("memories", "default_user")`, is scoped to the **user**
(currently a single fixed user, no login system) and persists across every
thread.

```python
USER_ID = "default_user"

async def save_memory(fact: str) -> str:
    await store.aput(("memories", USER_ID), str(uuid.uuid4()), {"text": fact})

async def search_memory(query: str) -> str:
    items = await store.asearch(("memories", USER_ID), limit=50)
    # naive keyword-overlap ranking, see below
```

## Why keyword-overlap ranking, not embeddings

`search_memory` ranks saved facts by counting query-term overlap in Python,
rather than using a vector embedding index. This avoids a second
model/embedding dependency and its cost, and keeps behavior deterministic
for a demo. Verified this actually discriminates correctly, not just
returning facts in save order: a saved "User is vegetarian" +
"User likes Rust programming language" pair correctly surfaces the Rust
fact first for a "what programming language" query, and the vegetarian
fact first for a "vegetarian diet" query.

## Agent-managed, by design

Both tools are deliberately exposed as explicit tool calls the LLM decides
to make (guided by the system prompt: save when the user shares a durable
fact, search when recalling something might help) rather than automatic
context-stuffing on every turn. This means memory read/write shows up as
real, visible `tool_call`/`tool_result` events in the UI -- the same
transparency as every other tool call.

## Verified behavior

A fact saved under one `thread_id` was correctly recalled from a
**completely different** `thread_id` in a later turn -- confirming the
store is genuinely user-scoped rather than accidentally thread-scoped.
Also confirmed to survive `docker compose restart backend` (Postgres-backed,
not in-memory).

!!! info "Browsing/editing saved memories"
    There's currently no UI to list, edit, or delete what's been saved --
    only the agent reads and writes via these two tools. Tracked as
    future work: [Roadmap &rarr; Access memories](../roadmap.md#access-memories).
