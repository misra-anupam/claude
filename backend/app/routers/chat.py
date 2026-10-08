import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langchain_core.messages import HumanMessage

from ..config import settings
from ..conversations import touch_conversation
from ..resilience.rate_limit import limiter
from ..schemas import ChatRequest
from ..streaming import get_adapter

router = APIRouter()


@router.post("/chat/stream", response_class=EventSourceResponse)
@limiter.limit("20/minute")
async def chat_stream(req: ChatRequest, request: Request) -> AsyncIterator[ServerSentEvent]:
    """
    MUST be an async generator function (not a regular function returning
    EventSourceResponse(some_generator())) -- confirmed by reading FastAPI's
    routing.py: the SSE wire encoding only kicks in when
    `_is_async_gen_callable(dependant.call)` is true for the route handler
    itself, with `response_class=EventSourceResponse` set on the decorator.
    Constructing EventSourceResponse manually and returning it falls back to
    generic StreamingResponse behavior, which crashes trying to `.encode()`
    a ServerSentEvent object directly (caught by an actual curl test against
    a running container, not just by reading docs).

    `@limiter.limit` below `@router.post` works here even though this is an
    async generator (not a coroutine function) -- verified by reading
    slowapi's extension.py: slowapi checks `asyncio.iscoroutinefunction`,
    which is False for async generators, so it wraps with a plain sync
    `functools.wraps`-decorated function that just calls-and-returns the
    generator unawaited. FastAPI's own `_is_async_gen_callable` check follows
    `__wrapped__` (via `inspect.unwrap`) back to the real generator function,
    so the SSE detection still works through the wrapper. Confirmed with a
    live curl against a running container, not just by reading both
    libraries' source.
    """
    runtime = request.app.state.runtime
    payload = {"messages": [HumanMessage(content=req.message)]}
    config = {"configurable": {"thread_id": req.thread_id}}
    adapter = get_adapter(settings.streaming_api_version)

    # Title is set once (from whichever message happens to be first in the
    # thread) and left alone after that; updated_at bumps on every message.
    await touch_conversation(settings.database_url, req.thread_id, req.message)

    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        adapter.run_and_translate(
            runtime.graph, payload, config, queue, runtime.breakers["openrouter"]
        )
    )
    try:
        while (item := await queue.get()) is not None:
            yield ServerSentEvent(event=item["event"], data=item["data"])
    finally:
        task.cancel()
