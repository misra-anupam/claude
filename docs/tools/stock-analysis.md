# Stock Analysis

`backend/app/tools/stock_analysis.py`

```python
@tool
async def stock_analysis(ticker: str, period: str = "1mo") -> str:
    """Get recent price performance for a stock ticker."""
```

Fetches via `yfinance.Ticker(ticker).history(period=period)`, computes
percent change over the period and a simple moving average (window = up to
5 periods).

## Resilience

Full cache &rarr; semaphore &rarr; breaker &rarr; retry stack. A bad ticker
(no price history) is treated as a **normal result, not a failure** -- it
returns a clear "No price history found" string and does **not** count
toward tripping the circuit breaker, since an invalid ticker is user error,
not a service outage. Only genuine fetch failures (network errors, Yahoo
endpoint issues) count as breaker failures.

## Verified behavior

- Real ticker (`TSLA`, `AAPL`): returns correct latest close, percent
  change, and SMA -- values spot-checked against real market data during
  development.
- Invalid ticker: returns a graceful "check the ticker symbol" message
  rather than crashing (confirmed with `NOTAREALTICKERXYZ`).
- Repeated identical request within the 5-minute cache window: returns
  instantly, confirmed via timing (first call ~0.5s, cached call ~0.00s).
- Simulated repeated failures (monkeypatched fetch function always
  raising): breaker opens on the 3rd call and returns the friendly
  "temporarily unavailable" message on the 3rd and subsequent calls, until
  the 30s reset window passes.
