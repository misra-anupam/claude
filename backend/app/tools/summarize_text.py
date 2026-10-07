from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.text_rank import TextRankSummarizer


def _fetch_page_text(url: str) -> str:
    resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator=" ")


@tool
def summarize_text(source: str, sentence_count: int = 5) -> str:
    """Summarize a URL's article text or a raw block of text.

    If `source` looks like a URL, fetches and extracts its page text first.
    Uses extractive TextRank summarization (deterministic, no extra LLM call).
    """
    parsed = urlparse(source)
    try:
        text = _fetch_page_text(source) if parsed.scheme in ("http", "https") else source
    except Exception as exc:  # noqa: BLE001 - network fetch can fail many ways
        return f"Could not fetch '{source}': {exc}"

    if not text.strip():
        return "Nothing to summarize (empty content)."

    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = TextRankSummarizer()
    sentences = summarizer(parser.document, sentence_count)
    if not sentences:
        return text[:500]
    return " ".join(str(s) for s in sentences)
