import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .agent import build_agent_graph
from .checkpointer import close_checkpointer, get_checkpointer
from .config import settings
from .db import wait_for_postgres
from .routers import chat, health
from .store import close_store, get_store

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await wait_for_postgres(settings.database_url)
    checkpointer = await get_checkpointer(settings.database_url)
    store = await get_store(settings.database_url)
    app.state.graph = build_agent_graph(checkpointer, store)
    yield
    await close_checkpointer()
    await close_store()


app = FastAPI(title="LangGraph OpenRouter Agent", lifespan=lifespan)
app.include_router(health.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
