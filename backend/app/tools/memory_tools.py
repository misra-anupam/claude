import uuid

from langchain_core.tools import tool
from langgraph.store.base import BaseStore

USER_ID = "default_user"  # single fixed user, no login system (per project scope)


def build_memory_tools(store: BaseStore) -> list:
    """Closures over the store, rather than relying on create_agent's `store=`
    kwarg + InjectedStore tool annotations -- this works regardless of exactly
    how that plumbing behaves, and keeps the memory tools' logic in one place.
    """

    @tool
    async def save_memory(fact: str) -> str:
        """Persist a durable fact about the user for future conversations
        (e.g. preferences, background, ongoing projects). Call this whenever
        the user shares something worth remembering long-term."""
        key = str(uuid.uuid4())
        await store.aput(("memories", USER_ID), key, {"text": fact})
        return f"Saved: {fact}"

    @tool
    async def search_memory(query: str) -> str:
        """Search previously saved facts about the user. Call this at the
        start of a conversation when recalling something the user may have
        told you before would help answer their question."""
        items = await store.asearch(("memories", USER_ID), limit=50)
        if not items:
            return "No memories saved yet."
        terms = [t for t in query.lower().split() if t]
        scored = sorted(
            items,
            key=lambda it: -sum(t in it.value["text"].lower() for t in terms),
        )
        return "\n".join(f"- {it.value['text']}" for it in scored[:5])

    return [save_memory, search_memory]
