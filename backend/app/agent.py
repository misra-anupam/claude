from langchain.agents import create_agent
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from .config import settings
from .tools import build_tool_list

SYSTEM_PROMPT = (
    "You are a helpful assistant with access to web search, a calculator, "
    "stock analysis, and text summarization tools, plus persistent memory "
    "tools (save_memory, search_memory) scoped to this one user. "
    "Call save_memory when the user shares a durable personal fact worth "
    "remembering across conversations. Call search_memory when recalling "
    "something the user may have told you before would help answer their "
    "question. Use tools whenever they would make your answer more accurate "
    "than relying on your own knowledge alone."
)


def build_agent_graph(checkpointer: BaseCheckpointSaver, store: BaseStore):
    model = ChatOpenRouter(
        model=settings.openrouter_model,
        openrouter_api_key=settings.openrouter_api_key,
        reasoning={"max_tokens": settings.reasoning_max_tokens},
        streaming=True,
    )
    tools = build_tool_list(store)
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        store=store,
    )
