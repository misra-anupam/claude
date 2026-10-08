import asyncio

import yfinance as yf
from aiobreaker import CircuitBreaker, CircuitBreakerError
from cachetools import TTLCache
from langchain_core.tools import tool

from ..resilience.retry import external_call_retry


def _fetch_sync(ticker: str, period: str) -> str:
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        # Not a transient failure -- don't retry/trip the breaker on a bad ticker.
        return f"__NO_DATA__{ticker}"

    first_close = float(hist["Close"].iloc[0])
    last_close = float(hist["Close"].iloc[-1])
    pct_change = (last_close - first_close) / first_close * 100
    sma_window = min(5, len(hist))
    sma = float(hist["Close"].rolling(window=sma_window).mean().iloc[-1])

    return (
        f"{ticker.upper()} over {period}: "
        f"latest close ${last_close:.2f}, "
        f"change {pct_change:+.2f}%, "
        f"{sma_window}-period SMA ${sma:.2f}"
    )


def build_stock_analysis_tool(
    cache: TTLCache, breaker: CircuitBreaker, sem: asyncio.Semaphore
):
    @external_call_retry()
    async def _fetch(ticker: str, period: str) -> str:
        async with sem:
            return await asyncio.to_thread(_fetch_sync, ticker, period)

    @tool
    async def stock_analysis(ticker: str, period: str = "1mo") -> str:
        """Get recent price performance for a stock ticker.

        `period` is a yfinance period string, e.g. "5d", "1mo", "3mo", "1y".
        Returns the latest close, percent change over the period, and a
        simple moving average.
        """
        key = (ticker, period)
        if key in cache:
            return cache[key]
        try:
            result = await breaker.call_async(_fetch, ticker, period)
        except CircuitBreakerError:
            return (
                f"Stock analysis is temporarily unavailable for {ticker} "
                "(too many recent failures) -- try again shortly."
            )
        except Exception as exc:  # noqa: BLE001 - Yahoo endpoints are known to be flaky
            return f"Could not fetch data for '{ticker}': {exc}"

        if result.startswith("__NO_DATA__"):
            return f"No price history found for '{ticker}' (check the ticker symbol)."

        cache[key] = result
        return result

    return stock_analysis
