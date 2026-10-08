from datetime import timedelta

from aiobreaker import CircuitBreaker

EXTERNAL_TOOL_NAMES = ("web_search", "stock_analysis", "summarize_text")
# Tools that need a breaker + concurrency cap but deliberately NOT a result
# cache -- sandbox_exec's output can depend on randomness/time/etc inside the
# executed code (so caching by code text would be surprising/wrong), and
# image_gen is inherently non-deterministic/creative per call.
NO_CACHE_TOOL_NAMES = ("sandbox_exec", "image_gen")


def build_breakers() -> dict[str, CircuitBreaker]:
    """One breaker per external-dependency tool, plus one for the OpenRouter
    model call itself. Opens after 3 consecutive failures, auto-resets after
    30s -- verified against the real aiobreaker==1.2.0 API (fail_max,
    timeout_duration kwargs; .call_async(func, *args, **kwargs) method).
    """
    names = (*EXTERNAL_TOOL_NAMES, *NO_CACHE_TOOL_NAMES, "openrouter")
    return {
        name: CircuitBreaker(fail_max=3, timeout_duration=timedelta(seconds=30))
        for name in names
    }
