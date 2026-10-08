import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import settings
from .sandbox import run_code

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Sandbox Executor")


class ExecuteRequest(BaseModel):
    code: str
    timeout: int = Field(default=10, ge=1, le=settings.max_timeout_seconds)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/execute")
async def execute(req: ExecuteRequest) -> dict:
    if len(req.code) > settings.max_code_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Code too long ({len(req.code)} chars, max {settings.max_code_chars}).",
        )
    return await run_code(req.code, req.timeout)
