from cachetools import TTLCache

from .circuit_breaker import EXTERNAL_TOOL_NAMES


def build_caches() -> dict[str, TTLCache]:
    """One TTLCache per external-dependency tool. TTLCache gives bounded size
    (LRU eviction) *and* time-based expiry together -- stock prices and
    search results go stale, so a plain LRU cache alone wouldn't be enough.
    """
    return {name: TTLCache(maxsize=256, ttl=300) for name in EXTERNAL_TOOL_NAMES}
