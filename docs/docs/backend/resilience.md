# Resilience

`backend/app/resilience/` -- `cache.py`, `circuit_breaker.py`, `retry.py`,
`rate_limit.py`. The four-layer pattern applied per tool is covered in
[Tools Overview](../tools/index.md#the-resilience-pattern); this page
covers the implementation and the two real bugs found wiring it up.

## Circuit breakers

```python title="backend/app/resilience/circuit_breaker.py"
EXTERNAL_TOOL_NAMES = ("web_search", "stock_analysis", "summarize_text")
NO_CACHE_TOOL_NAMES = ("sandbox_exec", "image_gen")

def build_breakers() -> dict[str, CircuitBreaker]:
    names = (*EXTERNAL_TOOL_NAMES, *NO_CACHE_TOOL_NAMES, "openrouter")
    return {name: CircuitBreaker(fail_max=3, timeout_duration=timedelta(seconds=30)) for name in names}
```

`aiobreaker`'s actual semantics (confirmed by testing against the real
library, not assumed from its docs): with `fail_max=N`, the **Nth**
failing call is the one that trips the breaker and raises
`CircuitBreakerError` for that call -- not the underlying exception.
Earlier failures (1 through N-1) propagate their real exception normally.
Calls after the breaker trips fail immediately with
`CircuitBreakerError("Timeout not elapsed yet...")` until
`timeout_duration` passes.

```text title="Verified: fail_max=2 against a function engineered to always fail"
call 1: RuntimeError("simulated failure")           # real error, breaker still closed
call 2: CircuitBreakerError("...opened.")             # the call that trips it
call 3: CircuitBreakerError("Timeout not elapsed...")  # fails fast
```

The one subtlety that caused a real bug: `.call_async(fn, ...)` only
registers a failure if `fn` **raises out** to it. See
[Streaming Design](../streaming.md#the-openrouter-circuit-breaker-needs-the-exception-to-escape)
for the full story of catching this in the OpenRouter breaker specifically.

## Caching

```python title="backend/app/resilience/cache.py"
def build_caches() -> dict[str, TTLCache]:
    return {name: TTLCache(maxsize=256, ttl=300) for name in EXTERNAL_TOOL_NAMES}
```

`cachetools.TTLCache` gives bounded size (LRU eviction) *and* time-based
expiry in one structure -- a plain LRU cache alone wouldn't be enough,
since stock prices and search results go stale well before the cache would
naturally evict them on size alone.

## Retry

```python title="backend/app/resilience/retry.py"
def external_call_retry():
    return retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.5, max=4), reraise=True)
```

Applied to the innermost fetch function of each tool, **inside** the
circuit breaker -- so a transient failure gets a few quick retries before
counting as one breaker failure, but repeated transient failures still
accumulate toward tripping it.

## Rate limiting

```python title="backend/app/resilience/rate_limit.py"
limiter = Limiter(key_func=get_remote_address)
```

Applied to the chat endpoint: `@limiter.limit("20/minute")`. Verified live
by firing 22 rapid requests against the real running stack: 19 succeeded,
the 20th and later got HTTP 429.

!!! danger "Real bug: slowapi + the SSE async-generator route"
    `routers/chat.py`'s route handler must be an async generator for
    FastAPI's native SSE encoding to activate at all (see
    [Streaming Design](../streaming.md#why-post-not-native-eventsource)).
    Stacking `@limiter.limit(...)` on top of that was a real question mark:
    does slowapi's decorator still work correctly on an async generator,
    not a coroutine function?

    Read `slowapi`'s `extension.py` to find out: it branches on
    `asyncio.iscoroutinefunction(func)`, which is **False** for an async
    generator function -- so it takes the "sync" branch, wrapping with a
    plain `functools.wraps`-decorated `def` that calls-and-returns the
    generator unawaited (correct -- calling an async generator function
    just returns the generator object, no await needed). FastAPI's own
    `_is_async_gen_callable` check follows `__wrapped__` (via
    `inspect.unwrap`) back through `functools.wraps` to the real generator
    function underneath, so the SSE detection still works through the
    wrapper.

    Confirmed with a live `curl` against a running container: the
    rate-limited, SSE-streaming, async-generator route works correctly --
    both the streaming and the 429-after-20-requests behavior hold
    simultaneously.
