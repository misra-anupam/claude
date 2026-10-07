from ddgs import DDGS
from langchain_core.tools import tool


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current information and return titles, URLs, and snippets."""
    try:
        results = DDGS().text(query, max_results=max_results)
    except Exception as exc:  # noqa: BLE001 - no-key search backend can be flaky
        return f"Web search failed: {exc}"
    if not results:
        return "No results found."
    lines = []
    for r in results:
        title = r.get("title", "")
        href = r.get("href", "")
        body = r.get("body", "")
        lines.append(f"- {title}\n  {href}\n  {body}")
    return "\n".join(lines)
