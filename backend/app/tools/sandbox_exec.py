import asyncio

import httpx
from aiobreaker import CircuitBreaker, CircuitBreakerError
from langchain_core.tools import tool

from ..config import settings
from ..resilience.retry import external_call_retry


def build_sandbox_exec_tool(
    http_client: httpx.AsyncClient, breaker: CircuitBreaker, sem: asyncio.Semaphore
):
    @external_call_retry()
    async def _call_executor(code: str, timeout: int) -> dict:
        async with sem:
            resp = await http_client.post(
                f"{settings.executor_url}/execute",
                json={"code": code, "timeout": timeout},
                timeout=timeout + 10,
            )
            resp.raise_for_status()
            return resp.json()

    @tool
    async def run_sandboxed_code(code: str, timeout: int = 10) -> str:
        """Execute Python code in an isolated, network-disabled sandbox
        container and return its stdout/stderr. Use for calculations, data
        processing, or logic too complex for the calculator tool. The
        sandbox has no network access and no access to any files outside
        itself -- it cannot reach the internet, this backend, or any other
        service. `timeout` is in seconds (max 20).
        """
        try:
            result = await breaker.call_async(_call_executor, code, timeout)
        except CircuitBreakerError:
            return "Code execution is temporarily unavailable (too many recent failures) -- try again shortly."
        except Exception as exc:  # noqa: BLE001 - surface any executor-side error to the model
            return f"Code execution failed: {exc}"

        if result.get("timed_out"):
            return f"Execution timed out after {timeout}s. Partial output:\n{result.get('output', '')}"
        return (
            f"Exit code: {result.get('exit_code')}\n"
            f"Output:\n{result.get('output', '')}"
        )

    return run_sandboxed_code
