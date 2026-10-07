from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

_cm = None
_saver: AsyncPostgresSaver | None = None


async def get_checkpointer(dsn: str) -> AsyncPostgresSaver:
    """Build (once) the Postgres-backed per-thread conversation checkpointer.

    `.from_conn_string` is an async context manager, not a plain constructor --
    confirmed by inspecting the installed `langgraph-checkpoint-postgres` source.
    `.setup()` is idempotent (CREATE TABLE IF NOT EXISTS under the hood), so it's
    safe to call on every backend boot.
    """
    global _cm, _saver
    if _saver is None:
        _cm = AsyncPostgresSaver.from_conn_string(dsn)
        _saver = await _cm.__aenter__()
        await _saver.setup()
    return _saver


async def close_checkpointer() -> None:
    global _cm, _saver
    if _cm is not None:
        await _cm.__aexit__(None, None, None)
        _cm = None
        _saver = None
