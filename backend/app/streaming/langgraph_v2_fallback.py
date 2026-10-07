"""Fallback streaming adapter using the "classic" stream_mode combo, in case
the v3 event-streaming API (langgraph_v3_adapter.py) doesn't hold up in
practice. Select via STREAMING_API_VERSION=v2.

Same `run_and_translate(graph, payload, config, queue)` signature as the v3
adapter, so routers/chat.py doesn't need to know which one is active.
"""

import asyncio
from typing import Any

from langchain_core.messages import AIMessageChunk, ToolMessage

from .sse_events import make_event


async def run_and_translate(
    graph: Any, payload: dict, config: dict, queue: "asyncio.Queue"
) -> None:
    try:
        async for stream_mode, chunk in graph.astream(
            payload, config=config, stream_mode=["messages", "updates"], version="v2"
        ):
            if stream_mode == "messages":
                msg_chunk, _metadata = chunk
                if isinstance(msg_chunk, AIMessageChunk):
                    if msg_chunk.content:
                        await queue.put(make_event("token", {"delta": msg_chunk.content}))
                    reasoning = msg_chunk.additional_kwargs.get("reasoning_details")
                    if reasoning:
                        await queue.put(make_event("thinking", {"delta": reasoning}))
            elif stream_mode == "updates":
                for node_output in chunk.values():
                    if not isinstance(node_output, dict):
                        continue
                    for msg in node_output.get("messages", []):
                        if isinstance(msg, ToolMessage):
                            await queue.put(
                                make_event(
                                    "tool_result",
                                    {"id": msg.tool_call_id, "result": msg.content},
                                )
                            )
                        elif getattr(msg, "tool_calls", None):
                            for call in msg.tool_calls:
                                await queue.put(
                                    make_event(
                                        "tool_call",
                                        {
                                            "id": call.get("id"),
                                            "name": call.get("name"),
                                            "args": call.get("args"),
                                        },
                                    )
                                )
        await queue.put(make_event("done", {}))
    except Exception as exc:  # noqa: BLE001 - must reach the client as an SSE error event
        await queue.put(make_event("error", {"message": str(exc)}))
    finally:
        await queue.put(None)
