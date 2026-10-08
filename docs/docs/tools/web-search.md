# Web Search

`backend/app/tools/web_search.py`

A no-API-key web search tool using the `ddgs` package (DuckDuckGo search --
note the package was renamed from `duckduckgo-search`; the import is
`from ddgs import DDGS`).

```python
@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current information and return titles, URLs, and snippets."""
```

## Resilience

Full cache &rarr; semaphore &rarr; breaker &rarr; retry stack (see
[Tools Overview](index.md#the-resilience-pattern)). Cache key is
`(query, max_results)`.

## Verified behavior

Live-tested with a real query ("James Webb Space Telescope latest news")
during development -- returned real titles/URLs/snippets from NASA and ESA
pages. Blocking failures (DuckDuckGo rate-limiting, network issues) return
a plain string ("Web search failed: ...") rather than raising, so the agent
can report the failure in its answer instead of crashing the turn.
