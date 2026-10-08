"""
All v3 event-streaming attribute access lives in this file only.

Verified against the real installed `langgraph==1.2.14` source (not just
docs) by reading `langgraph/stream/*.py` and
`langchain_core/language_models/chat_model_stream.py` directly, and by
driving a toy graph (a fake chat model + create_agent + a real tool) through
this exact code path during development, with no OpenRouter API key needed.
Ground truth, not assumption:

- `stream_events(version="v3")` natively registers `values`, `messages`,
  `lifecycle`, `subgraphs`. There is NO native `.tools` channel.
- `message.tool_calls` (on each `ChatModelStream` from `stream.messages`) is
  "async iterable, awaitable for finalized list" -- the model-side tool-call
  *request*, not the tool's execution result. Using `await message.tool_calls`
  after draining `.text`/`.reasoning` gives the finalized
  `[{"id":..., "name":..., "args":...}, ...]` -- this is the real source for
  `tool_call` (call-started) SSE events.
- The tool's execution *result* only shows up via the opt-in `updates`
  projection: pass `transformers=[UpdatesTransformer]`
  (`from langgraph.stream import UpdatesTransformer`), then
  `async for update in stream.updates:` -- each item is a dict keyed by node
  name (e.g. `{"tools": {"messages": [ToolMessage(...), ...]}}`); scan the
  nested `"messages"` lists for `ToolMessage` instances and match
  `.tool_call_id`. This is the real source for `tool_result` SSE events.
  Confirmed empirically for both a single tool call and two simultaneous
  tool calls -- correct id-matched ordering in both cases.

If a future langgraph release changes this shape, only this file needs to
change -- routers/chat.py and sse_events.py are agnostic to which adapter
produced the queue items.
"""

import asyncio
from typing import Any

from aiobreaker import CircuitBreaker, CircuitBreakerError
from langchain_core.messages import ToolMessage
from langgraph.stream import UpdatesTransformer

from ..utils.reasoning_merge import merge_reasoning_details
from .sse_events import make_event


async def run_and_translate(
    graph: Any,
    payload: dict,
    config: dict,
    queue: "asyncio.Queue",
    openrouter_breaker: CircuitBreaker | None = None,
) -> None:
    """`openrouter_breaker`, when given, wraps the whole turn (not each
    individual model call within a multi-tool-round turn -- threading a
    breaker through LangGraph's internal model node would require far more
    invasive changes for marginal benefit). The exception must propagate out
    of `_drive_graph` uncaught so the breaker actually registers it as a
    failure; this function is the only place that translates failures into
    an `error` SSE event.
    """
    try:
        if openrouter_breaker is not None:
            await openrouter_breaker.call_async(_drive_graph, graph, payload, config, queue)
        else:
            await _drive_graph(graph, payload, config, queue)
        await queue.put(make_event("done", {}))
    except CircuitBreakerError:
        await queue.put(
            make_event(
                "error",
                {"message": "OpenRouter is temporarily unavailable -- try again shortly."},
            )
        )
    except Exception as exc:  # noqa: BLE001 - must reach the client as an SSE error event
        await queue.put(make_event("error", {"message": str(exc)}))
    finally:
        await queue.put(None)


async def _drive_graph(graph: Any, payload: dict, config: dict, queue: "asyncio.Queue") -> None:
    stream = await graph.astream_events(
        payload, config=config, version="v3", transformers=[UpdatesTransformer]
    )

    async def consume_messages() -> None:
        async for message in stream.messages:
            async def pump_reasoning() -> None:
                frags: list[Any] = []
                async for chunk in message.reasoning:
                    frags.append(chunk)
                    await queue.put(make_event("thinking", {"delta": chunk}))
                if frags and isinstance(frags[0], dict):
                    merge_reasoning_details(frags)

            async def pump_text() -> None:
                async for chunk in message.text:
                    await queue.put(make_event("token", {"delta": chunk}))

            await asyncio.gather(pump_reasoning(), pump_text())

            tool_calls = await message.tool_calls
            for call in tool_calls or []:
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

    async def consume_updates() -> None:
        async for update in stream.updates:
            for node_output in update.values():
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

    await asyncio.gather(consume_messages(), consume_updates())
