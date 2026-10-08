import asyncio

import httpx
from aiobreaker import CircuitBreaker
from cachetools import TTLCache
from langgraph.store.base import BaseStore

from .calculator import calculator
from .chart_tools import build_chart_tools
from .image_gen import build_image_gen_tool
from .memory_tools import build_memory_tools
from .sandbox_exec import build_sandbox_exec_tool
from .stock_analysis import build_stock_analysis_tool
from .summarize_text import build_summarize_text_tool
from .web_search import build_web_search_tool


def build_tool_list(
    store: BaseStore,
    breakers: dict[str, CircuitBreaker],
    tool_semaphores: dict[str, asyncio.Semaphore],
    caches: dict[str, TTLCache],
    http_client: httpx.AsyncClient,
    artifacts: TTLCache,
) -> list:
    return [
        build_web_search_tool(
            caches["web_search"], breakers["web_search"], tool_semaphores["web_search"]
        ),
        calculator,
        build_stock_analysis_tool(
            caches["stock_analysis"],
            breakers["stock_analysis"],
            tool_semaphores["stock_analysis"],
        ),
        build_summarize_text_tool(
            http_client, caches["summarize_text"], breakers["summarize_text"]
        ),
        build_sandbox_exec_tool(
            http_client, breakers["sandbox_exec"], tool_semaphores["sandbox_exec"]
        ),
        *build_chart_tools(artifacts),
        build_image_gen_tool(
            http_client, breakers["image_gen"], tool_semaphores["image_gen"], artifacts
        ),
        *build_memory_tools(store),
    ]
