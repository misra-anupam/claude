"""Defensive mitigation for OpenRouter/langchain-openrouter streaming issue
#36400: streamed `reasoning_details` fragments can be list-concatenated by
`AIMessageChunk.__add__` instead of merged into single entries. When that
fragmented payload is round-tripped on the next multi-turn request,
OpenRouter rejects it with a 400. This re-coalesces fragments by index
before they're checkpointed/replayed, independent of whether the pinned
`langchain-openrouter` version already fixes this upstream.
"""

from typing import Any

from langchain_core.callbacks.base import BaseCallbackHandler


def merge_reasoning_details(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coalesce streamed reasoning_details fragments by `index`, concatenating
    text-bearing fields in arrival order. Idempotent on an already-whole list.
    """
    merged: dict[int, dict[str, Any]] = {}
    for frag in fragments:
        idx = frag.get("index", 0)
        if idx not in merged:
            merged[idx] = dict(frag)
        else:
            for key in ("text", "data", "signature"):
                if key in frag:
                    merged[idx][key] = merged[idx].get(key, "") + frag[key]
    return [merged[i] for i in sorted(merged)]


class ReasoningDetailsMergeCallback(BaseCallbackHandler):
    """Registered on the ChatOpenRouter instance; re-coalesces
    `reasoning_details` on every completed LLM call before it lands in
    checkpointed state.
    """

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        for generation_list in getattr(response, "generations", []):
            for generation in generation_list:
                message = getattr(generation, "message", None)
                if message is None:
                    continue
                kwargs_ = getattr(message, "additional_kwargs", None)
                if kwargs_ and "reasoning_details" in kwargs_:
                    kwargs_["reasoning_details"] = merge_reasoning_details(
                        kwargs_["reasoning_details"]
                    )
