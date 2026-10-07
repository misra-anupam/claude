import asyncio
import logging

import psycopg

logger = logging.getLogger(__name__)


async def wait_for_postgres(dsn: str, timeout: float = 30.0) -> None:
    """Retry a plain connection until Postgres accepts it or `timeout` elapses.

    Belt-and-suspenders on top of docker-compose's `pg_isready` healthcheck --
    guards against the backend container winning a startup race anyway.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    delay = 0.5
    last_error: Exception | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            conn = await psycopg.AsyncConnection.connect(dsn, connect_timeout=5)
            await conn.close()
            return
        except Exception as exc:  # noqa: BLE001 - genuinely want to retry on anything
            last_error = exc
            logger.info("Postgres not ready yet (%s), retrying in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 3.0)
    raise RuntimeError(f"Postgres never became ready within {timeout}s") from last_error
