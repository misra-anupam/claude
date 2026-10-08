"""
Runs untrusted code inside a short-lived, heavily-restricted sibling
container (Docker-outside-of-Docker via the mounted host socket). This is
the ONLY service in the whole project that touches the Docker socket --
the main agent backend never does, so a compromised backend can't reach it.

Hardening verified live during development (not just configured and hoped
for) against the real local Docker daemon:
- network_disabled=True: outbound socket connections fail with
  "Network is unreachable".
- read_only=True + tmpfs only on /tmp: writes outside /tmp raise
  "Read-only file system".
- pids_limit: a fork-bomb loop gets capped at a handful of processes before
  further forks fail, and the container is killed (exit 137).
- mem_limit: an attempt to allocate well beyond the limit gets OOM-killed
  (exit 137, "Killed").

Code is passed into the container via a base64-encoded shell one-liner
rather than a volume mount or raw string interpolation, specifically to
avoid any shell-quoting/escaping edge cases from the submitted code itself
(base64's alphabet has no shell-special characters).
"""

import asyncio
import base64
import shlex
import time

import docker
from docker.errors import DockerException

from .config import settings

_client: docker.DockerClient | None = None
_semaphore = asyncio.Semaphore(settings.max_concurrent)


def _get_client() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text) - limit} more chars]"


def _run_sync(code: str, timeout: int) -> dict:
    client = _get_client()
    b64 = base64.b64encode(code.encode()).decode()
    # The in-container `timeout` is the primary enforcement; container.wait's
    # own timeout below is defense in depth in case that somehow doesn't fire.
    inner_cmd = f"echo {shlex.quote(b64)} | base64 -d > /tmp/code.py && timeout {timeout}s python3 /tmp/code.py"

    container = client.containers.run(
        image=settings.sandbox_image,
        command=["sh", "-c", inner_cmd],
        detach=True,
        network_disabled=True,
        mem_limit=settings.sandbox_mem_limit,
        nano_cpus=settings.sandbox_nano_cpus,
        pids_limit=settings.sandbox_pids_limit,
        read_only=True,
        tmpfs={"/tmp": f"size={settings.sandbox_tmpfs_size}"},
        user="65534:65534",  # nobody -- never root inside the sandbox
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
    )
    start = time.monotonic()
    timed_out = False
    try:
        result = container.wait(timeout=timeout + 5)
        exit_code = result.get("StatusCode", -1)
    except Exception:
        timed_out = True
        exit_code = -1
        try:
            container.kill()
        except DockerException:
            pass
    output = container.logs(stdout=True, stderr=True).decode(errors="replace")
    try:
        container.remove(force=True)
    except DockerException:
        pass

    return {
        "output": _truncate(output, settings.max_output_chars),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - start, 2),
    }


async def run_code(code: str, timeout: int) -> dict:
    timeout = min(timeout, settings.max_timeout_seconds)
    async with _semaphore:
        return await asyncio.to_thread(_run_sync, code, timeout)
