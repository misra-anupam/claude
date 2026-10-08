"""
Ephemeral storage for binary tool output (chart PNGs now; generated images
and PDFs in later phases). Tool results that go back to the LLM stay small
(a short description + an artifact_id) -- the actual bytes are served
separately over plain HTTP via GET /api/artifacts/{id}, which the frontend
points an <img> tag or download link at directly rather than threading
binary data through the SSE token stream or the LLM's own context.

In-memory TTLCache, not a real object store -- correct scope for a study
project (this is not meant to survive a backend restart, unlike the
Postgres-backed long-term memory).
"""

import uuid

from cachetools import TTLCache


def build_artifact_store() -> TTLCache:
    return TTLCache(maxsize=256, ttl=3600)


def save_artifact(store: TTLCache, data: bytes, content_type: str) -> str:
    artifact_id = uuid.uuid4().hex
    store[artifact_id] = (data, content_type)
    return artifact_id


def get_artifact(store: TTLCache, artifact_id: str) -> tuple[bytes, str] | None:
    return store.get(artifact_id)
