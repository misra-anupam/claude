import yfinance as yf
from langchain_core.tools import tool


@tool
def stock_analysis(ticker: str, period: str = "1mo") -> str:
    """Get recent price performance for a stock ticker.

    `period` is a yfinance period string, e.g. "5d", "1mo", "3mo", "1y".
    Returns the latest close, percent change over the period, and a simple
    moving average.
    """
    try:
        hist = yf.Ticker(ticker).history(period=period)
    except Exception as exc:  # noqa: BLE001 - Yahoo endpoints are known to be flaky
        return f"Could not fetch data for '{ticker}': {exc}"
    if hist.empty:
        return f"No price history found for '{ticker}' (check the ticker symbol)."

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
