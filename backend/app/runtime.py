import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from aiobreaker import CircuitBreaker
from cachetools import TTLCache
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from .agent import build_agent_graph
from .checkpointer import get_checkpointer
from .config import Settings
from .db import wait_for_postgres
from .resilience.cache import build_caches
from .resilience.circuit_breaker import EXTERNAL_TOOL_NAMES, build_breakers
from .store import get_store


@dataclass
class AgentRuntime:
    """Everything the agent needs, built once at startup and held on
    app.state.runtime -- nothing below is rebuilt per request."""

    graph: Any
    checkpointer: BaseCheckpointSaver
    store: BaseStore
    http_client: httpx.AsyncClient
    caches: dict[str, TTLCache]
    breakers: dict[str, CircuitBreaker]
    tool_semaphores: dict[str, asyncio.Semaphore]


async def build_runtime(settings: Settings) -> AgentRuntime:
    await wait_for_postgres(settings.database_url)
    checkpointer = await get_checkpointer(settings.database_url)
    store = await get_store(settings.database_url)
    http_client = httpx.AsyncClient(timeout=10)
    caches = build_caches()
    breakers = build_breakers()
    # Caps concurrent outbound calls to the free/no-key services so a burst of
    # parallel tool calls doesn't trigger upstream rate-limiting/IP bans.
    tool_semaphores = {name: asyncio.Semaphore(4) for name in EXTERNAL_TOOL_NAMES}
    graph = build_agent_graph(
        checkpointer, store, breakers, tool_semaphores, caches, http_client
    )
    return AgentRuntime(
        graph=graph,
        checkpointer=checkpointer,
        store=store,
        http_client=http_client,
        caches=caches,
        breakers=breakers,
        tool_semaphores=tool_semaphores,
    )
