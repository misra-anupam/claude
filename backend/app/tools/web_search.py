import asyncio

from aiobreaker import CircuitBreaker, CircuitBreakerError
from cachetools import TTLCache
from ddgs import DDGS
from langchain_core.tools import tool

from ..resilience.retry import external_call_retry


def _search_sync(query: str, max_results: int) -> str:
    results = DDGS().text(query, max_results=max_results)
    if not results:
        return "__NO_RESULTS__"
    lines = []
    for r in results:
        title = r.get("title", "")
        href = r.get("href", "")
        body = r.get("body", "")
        lines.append(f"- {title}\n  {href}\n  {body}")
    return "\n".join(lines)


def build_web_search_tool(cache: TTLCache, breaker: CircuitBreaker, sem: asyncio.Semaphore):
    @external_call_retry()
    async def _fetch(query: str, max_results: int) -> str:
        async with sem:
            return await asyncio.to_thread(_search_sync, query, max_results)

    @tool
    async def web_search(query: str, max_results: int = 5) -> str:
        """Search the web for current information and return titles, URLs, and snippets."""
        key = (query, max_results)
        if key in cache:
            return cache[key]
        try:
            result = await breaker.call_async(_fetch, query, max_results)
        except CircuitBreakerError:
            return "Web search is temporarily unavailable (too many recent failures) -- try again shortly."
        except Exception as exc:  # noqa: BLE001 - no-key search backend can be flaky
            return f"Web search failed: {exc}"

        if result == "__NO_RESULTS__":
            return "No results found."

        cache[key] = result
        return result

    return web_search
