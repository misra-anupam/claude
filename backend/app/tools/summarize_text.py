from urllib.parse import urlparse

import httpx
from aiobreaker import CircuitBreaker, CircuitBreakerError
from bs4 import BeautifulSoup
from cachetools import TTLCache
from langchain_core.tools import tool
from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.text_rank import TextRankSummarizer

from ..resilience.retry import external_call_retry


async def _fetch_page_text(http_client: httpx.AsyncClient, url: str) -> str:
    resp = await http_client.get(url, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator=" ")


def _summarize_sync(text: str, sentence_count: int) -> str:
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = TextRankSummarizer()
    sentences = summarizer(parser.document, sentence_count)
    if not sentences:
        return text[:500]
    return " ".join(str(s) for s in sentences)


def build_summarize_text_tool(
    http_client: httpx.AsyncClient, cache: TTLCache, breaker: CircuitBreaker
):
    @external_call_retry()
    async def _fetch(url: str) -> str:
        return await _fetch_page_text(http_client, url)

    @tool
    async def summarize_text(source: str, sentence_count: int = 5) -> str:
        """Summarize a URL's article text or a raw block of text.

        If `source` looks like a URL, fetches and extracts its page text
        first. Uses extractive TextRank summarization (deterministic, no
        extra LLM call).
        """
        parsed = urlparse(source)
        is_url = parsed.scheme in ("http", "https")

        if is_url:
            cache_key = ("url", source, sentence_count)
            if cache_key in cache:
                return cache[cache_key]
            try:
                text = await breaker.call_async(_fetch, source)
            except CircuitBreakerError:
                return "Summarization is temporarily unavailable (too many recent fetch failures) -- try again shortly."
            except Exception as exc:  # noqa: BLE001 - network fetch can fail many ways
                return f"Could not fetch '{source}': {exc}"
        else:
            text = source
            cache_key = None

        if not text.strip():
            return "Nothing to summarize (empty content)."

        summary = _summarize_sync(text, sentence_count)
        if cache_key is not None:
            cache[cache_key] = summary
        return summary

    return summarize_text
