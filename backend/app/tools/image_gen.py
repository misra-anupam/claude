"""
Image generation via OpenRouter -- the SAME OPENROUTER_API_KEY already used
for the main chat model, no separate Gemini key needed. Verified live:
OpenRouter proxies Google's Gemini 2.5 Flash Image ("Nano Banana") directly
over its standard chat completions endpoint.

Bypasses `ChatOpenRouter`/LangChain deliberately -- confirmed live that the
installed langchain-openrouter==0.2.9 doesn't parse OpenRouter's image-output
response shape (`choices[0].message.images[]`) into any LangChain message
attribute (checked .content, .content_blocks, .additional_kwargs,
.response_metadata -- all empty/missing the image data even though the
response was genuinely billed for a generated image). Calling OpenRouter's
REST API directly with httpx and parsing the raw JSON sidesteps that gap.
"""

import asyncio
import base64
import json

import httpx
from aiobreaker import CircuitBreaker, CircuitBreakerError
from cachetools import TTLCache
from langchain_core.tools import tool

from ..artifacts import save_artifact
from ..config import settings
from ..resilience.retry import external_call_retry


def _parse_data_uri(data_uri: str) -> tuple[bytes, str]:
    header, _, b64data = data_uri.partition(",")
    content_type = "image/png"
    if header.startswith("data:"):
        meta = header[len("data:") :]
        content_type = meta.split(";")[0] or "image/png"
    return base64.b64decode(b64data), content_type


def build_image_gen_tool(
    http_client: httpx.AsyncClient,
    breaker: CircuitBreaker,
    sem: asyncio.Semaphore,
    artifact_store: TTLCache,
):
    @external_call_retry()
    async def _call_openrouter(prompt: str) -> dict:
        async with sem:
            resp = await http_client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json={
                    "model": settings.image_gen_model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()

    @tool
    async def generate_image(prompt: str) -> str:
        """Generate an image from a text description and return a reference
        to it for inline display. Use for illustrations, diagrams-as-art,
        or any visual the user asks for that isn't a data chart (use
        generate_chart for that instead).
        """
        try:
            data = await breaker.call_async(_call_openrouter, prompt)
        except CircuitBreakerError:
            return "Image generation is temporarily unavailable (too many recent failures) -- try again shortly."
        except Exception as exc:  # noqa: BLE001 - surface any API error to the model
            return f"Image generation failed: {exc}"

        images = (data.get("choices") or [{}])[0].get("message", {}).get("images") or []
        if not images:
            # Model responded but didn't generate an image (e.g. refused the
            # prompt) -- the text response is still useful context.
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return f"No image was generated. Model response: {text}"

        url = images[0].get("image_url", {}).get("url", "")
        try:
            image_bytes, content_type = _parse_data_uri(url)
        except Exception as exc:  # noqa: BLE001 - malformed response is still a tool failure, not a crash
            return f"Received an image response in an unexpected format: {exc}"

        artifact_id = save_artifact(artifact_store, image_bytes, content_type)
        return json.dumps(
            {
                "text": f"Generated an image for: {prompt}",
                "artifact_id": artifact_id,
                "content_type": content_type,
            }
        )

    return generate_image
