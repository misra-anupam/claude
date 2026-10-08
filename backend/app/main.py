import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .checkpointer import close_checkpointer
from .config import settings
from .resilience.rate_limit import limiter
from .routers import artifacts, chat, health
from .runtime import build_runtime
from .store import close_store

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = await build_runtime(settings)
    yield
    await app.state.runtime.http_client.aclose()
    await close_checkpointer()
    await close_store()


app = FastAPI(title="LangGraph OpenRouter Agent", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(health.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(artifacts.router, prefix="/api")
