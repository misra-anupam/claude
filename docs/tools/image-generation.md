# Image Generation

`backend/app/tools/image_gen.py`

```python
@tool
async def generate_image(prompt: str) -> str:
    """Generate an image from a text description."""
```

## No separate Gemini API key needed

This was a mid-session discovery, not the original plan. The original
design called for a direct Google Gemini API key
(`GEMINI_API_KEY`). While scoping that work, it turned out OpenRouter
**proxies Google's Gemini 2.5 Flash Image model directly**
(`google/gemini-2.5-flash-image`, nicknamed "Nano Banana") over its
standard chat completions endpoint -- meaning the same `OPENROUTER_API_KEY`
already used for the chat model works for image generation too.

Confirmed live, with a real key, before committing to this design:

```python
resp = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {api_key}"},
    json={"model": "google/gemini-2.5-flash-image",
          "messages": [{"role": "user", "content": "..."}]},
)
# resp.json()["usage"]["cost"] was genuinely non-zero -- an image was billed
```

## Why this tool bypasses `ChatOpenRouter`

`ChatOpenRouter` (the LangChain wrapper, `langchain-openrouter==0.2.9`) is
used everywhere else in this project (see [Agent & Model](../backend/agent.md)).
For image generation specifically, it silently drops the response.

Confirmed by inspecting every attribute of the returned `AIMessage`:
`.content`, `.content_blocks`, `.additional_kwargs`, `.response_metadata`
were all checked -- none contained the image data, even though the API
response (checked via raw `httpx`, bypassing the wrapper) genuinely was
billed for a generated image. The real image data lives at
`choices[0].message.images[0].image_url.url` (a `data:image/png;base64,...`
URI) in OpenRouter's raw JSON response -- a field `ChatOpenRouter` doesn't
yet parse into any LangChain message attribute.

Fixed by calling OpenRouter's REST API directly with `httpx` for this one
tool, parsing the base64 data URI manually:

```python
async def _call_openrouter(prompt: str) -> dict:
    resp = await http_client.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json={"model": settings.image_gen_model, "messages": [{"role": "user", "content": prompt}]},
    )
    return resp.json()

# then: images[0]["image_url"]["url"] -> base64.b64decode(...) -> save_artifact(...)
```

## Delivery

Reuses the exact same
[artifact pattern](index.md#artifacts-how-binary-output-reaches-the-browser)
as `generate_chart` -- same `{text, artifact_id, content_type}` JSON shape,
rendered by the exact same frontend code path. No new frontend work was
needed when this tool was added.

## Resilience

Deliberately **not cached** (see `NO_CACHE_TOOL_NAMES`) -- image generation
is inherently creative/non-deterministic, so caching by prompt text would
be surprising. Full semaphore &rarr; breaker &rarr; retry stack otherwise.

## Verified behavior

A real prompt ("a small red fox sitting in a snowy forest, cartoon style")
produced a genuine, well-composed 1024x1024 PNG, confirmed visually, served
correctly end to end through the artifact endpoint.

!!! info "Configuration"
    The model is set via `IMAGE_GEN_MODEL` (default
    `google/gemini-2.5-flash-image`), separate from `OPENROUTER_MODEL` (the
    main chat model) -- these are two different OpenRouter model slugs
    serving two different purposes.
