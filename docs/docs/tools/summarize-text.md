# Summarize Text

`backend/app/tools/summarize_text.py`

```python
@tool
async def summarize_text(source: str, sentence_count: int = 5) -> str:
    """Summarize a URL's article text or a raw block of text."""
```

If `source` parses as an `http`/`https` URL, fetches it (via the shared
`httpx.AsyncClient` on `AgentRuntime`) and strips `<script>`, `<style>`,
`<nav>`, `<footer>`, `<header>`, `<aside>` tags before extracting text.
Otherwise treats `source` as raw text directly.

## Why extractive summarization, not a second LLM call

Summarization uses `sumy`'s **TextRank** algorithm -- a deterministic,
graph-based extractive method that picks existing sentences from the
source text, rather than generating new ones. This was a deliberate choice
over piping the text through a second OpenRouter call:

- No extra OpenRouter spend per summarization call
- No nondeterminism in a demo path (same input, same output, every time)
- Still genuinely useful for "summarize this article" requests

The tradeoff: it's less fluent than an abstractive (LLM-generated) summary,
and can occasionally surface boilerplate the tag-stripping didn't catch
(observed on Wikipedia pages: some sidebar/navigation text without
semantic `<nav>` tags occasionally leaks through). Good enough for a demo,
not tuned further.

## Resilience

Full cache &rarr; breaker &rarr; retry stack (no separate semaphore --
`httpx.AsyncClient`'s own connection pooling handles concurrency here). NLTK's
`punkt` tokenizer data is baked into the Docker image at build time
specifically so this tool never needs outbound network access just to
tokenize sentences.

## Verified behavior

Live-tested against a real Wikipedia article (Retrieval-augmented
generation) -- produced a coherent few-sentence extractive summary, not a
raw text dump.
