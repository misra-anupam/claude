from langgraph.store.postgres.aio import AsyncPostgresStore

_cm = None
_store: AsyncPostgresStore | None = None


async def get_store(dsn: str) -> AsyncPostgresStore:
    """Build (once) the Postgres-backed long-term memory store (user-scoped,
    not thread-scoped -- this is what survives across conversation threads and
    backend restarts). Same async-context-manager + idempotent `.setup()`
    pattern as the checkpointer.
    """
    global _cm, _store
    if _store is None:
        _cm = AsyncPostgresStore.from_conn_string(dsn)
        _store = await _cm.__aenter__()
        await _store.setup()
    return _store


async def close_store() -> None:
    global _cm, _store
    if _cm is not None:
        await _cm.__aexit__(None, None, None)
        _cm = None
        _store = None
