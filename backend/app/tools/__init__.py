from langgraph.store.base import BaseStore

from .calculator import calculator
from .memory_tools import build_memory_tools
from .stock_analysis import stock_analysis
from .summarize_text import summarize_text
from .web_search import web_search


def build_tool_list(store: BaseStore) -> list:
    return [
        web_search,
        calculator,
        stock_analysis,
        summarize_text,
        *build_memory_tools(store),
    ]
