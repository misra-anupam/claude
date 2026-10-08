import asyncio

import httpx
from aiobreaker import CircuitBreaker
from cachetools import TTLCache
from langchain.agents import create_agent
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from .config import settings
from .tools import build_tool_list
from .utils.reasoning_merge import ReasoningDetailsMergeCallback

SYSTEM_PROMPT = (
    "You are a helpful assistant with access to web search, a calculator, "
    "stock analysis, text summarization, a sandboxed Python code execution "
    "tool (run_sandboxed_code) for anything too complex for the calculator, "
    "chart/diagram generation tools (generate_chart for bar/line/pie/"
    "scatter charts from data, generate_diagram for Mermaid flowcharts), "
    "an image generation tool (generate_image) for illustrations and other "
    "visuals that aren't data charts, and document generation tools "
    "(generate_html, generate_pdf) for downloadable report-style documents, "
    "plus persistent memory tools (save_memory, search_memory) scoped to "
    "this one user. "
    "Call save_memory when the user shares a durable personal fact worth "
    "remembering across conversations. Call search_memory when recalling "
    "something the user may have told you before would help answer their "
    "question. Use tools whenever they would make your answer more accurate "
    "than relying on your own knowledge alone."
)


def build_agent_graph(
    checkpointer: BaseCheckpointSaver,
    store: BaseStore,
    breakers: dict[str, CircuitBreaker],
    tool_semaphores: dict[str, asyncio.Semaphore],
    caches: dict[str, TTLCache],
    http_client: httpx.AsyncClient,
    artifacts: TTLCache,
):
    # NOTE: deliberately NOT using `.with_retry()` here -- it wraps the model in
    # a generic `RunnableRetry`, which doesn't expose `.bind_tools()`, and
    # `create_agent` calls `model.bind_tools(...)` internally. Confirmed by a
    # live run: "'RunnableRetry' object has no attribute 'bind_tools'".
    # ChatOpenRouter's own native `max_retries` field achieves the same retry
    # goal without that incompatibility.
    model = ChatOpenRouter(
        model=settings.openrouter_model,
        openrouter_api_key=settings.openrouter_api_key,
        reasoning={"effort": settings.reasoning_effort},
        streaming=True,
        model_kwargs={"parallel_tool_calls": True},
        max_retries=3,
        callbacks=[ReasoningDetailsMergeCallback()],
    )

    tools = build_tool_list(
        store, breakers, tool_semaphores, caches, http_client, artifacts
    )
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        store=store,
    )
