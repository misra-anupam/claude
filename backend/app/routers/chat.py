import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langchain_core.messages import HumanMessage

from ..config import settings
from ..schemas import ChatRequest
from ..streaming import get_adapter

router = APIRouter()


@router.post("/chat/stream", response_class=EventSourceResponse)
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
    """
    graph = request.app.state.graph
    payload = {"messages": [HumanMessage(content=req.message)]}
    config = {"configurable": {"thread_id": req.thread_id}}
    adapter = get_adapter(settings.streaming_api_version)

    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(adapter.run_and_translate(graph, payload, config, queue))
    try:
        while (item := await queue.get()) is not None:
            yield ServerSentEvent(event=item["event"], data=item["data"])
    finally:
        task.cancel()
