"""
Lightweight conversation metadata for the sidebar -- a small dedicated table
(thread_id, title, timestamps) rather than reaching into the LangGraph
checkpointer's internal schema, which is an implementation detail of
langgraph-checkpoint-postgres that could change across versions. The actual
message history for a thread is still read from the checkpointer directly
(see get_conversation_messages) -- this table only tracks "which threads
exist and when were they last touched," for the sidebar list.
"""

import psycopg
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from psycopg.rows import dict_row


async def setup_conversations_table(dsn: str) -> None:
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                thread_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


async def touch_conversation(dsn: str, thread_id: str, first_message: str) -> None:
    """Create the conversation row (title = first message, truncated) if it
    doesn't exist yet, or just bump updated_at if it does -- title is set
    once, from whatever the first message in the thread was.
    """
    title = " ".join(first_message.split())[:60] or "New conversation"
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute(
            """
            INSERT INTO conversations (thread_id, title, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (thread_id) DO UPDATE SET updated_at = now()
            """,
            (thread_id, title),
        )


async def list_conversations(dsn: str) -> list[dict]:
    async with await psycopg.AsyncConnection.connect(
        dsn, autocommit=True, row_factory=dict_row
    ) as conn:
        cur = await conn.execute(
            "SELECT thread_id, title, updated_at FROM conversations "
            "ORDER BY updated_at DESC LIMIT 200"
        )
        rows = await cur.fetchall()
        return [
            {
                "thread_id": r["thread_id"],
                "title": r["title"],
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]


def _extract_text(content) -> str:
    """AIMessage.content can be a plain string or a list of content blocks
    (text/reasoning/tool_call/...) -- verified live against real stored
    checkpoints. For the history replay view we only want the final answer
    text, not reasoning or tool-call blocks (those aren't re-animated on
    reload, matching how most chat apps show history as static text)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


async def get_conversation_messages(
    checkpointer: BaseCheckpointSaver, thread_id: str
) -> list[dict]:
    config = {"configurable": {"thread_id": thread_id}}
    tup = await checkpointer.aget_tuple(config)
    if tup is None:
        return []
    messages = tup.checkpoint.get("channel_values", {}).get("messages", [])
    result = []
    for m in messages:
        if isinstance(m, HumanMessage):
            result.append({"role": "user", "content": _extract_text(m.content)})
        elif isinstance(m, AIMessage):
            text = _extract_text(m.content)
            if text.strip():
                result.append({"role": "assistant", "content": text})
    return result
