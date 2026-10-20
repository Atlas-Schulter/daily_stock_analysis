"""Daily close-to-close stock risk checks and optional Discord alerts."""
import json
import math
import os
import urllib.request

try:
    from src.alert_state import AlertState
except ModuleNotFoundError:
    from alert_state import AlertState


def check_risk(stock_code: str, daily_change: float, threshold: float = 5.0):
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be positive and finite")
    if not math.isfinite(daily_change):
        raise ValueError("daily_change must be finite")
    if daily_change <= -threshold:
        return (f"⚠️ Stock Risk Alert\nStock: {stock_code}\n"
                f"Daily Change: {daily_change:.2f}%\nThreshold: -{threshold:.2f}%")
    return None


def check_risk_from_quote(quote: dict, threshold: float = 5.0):
    return check_risk(quote["code"], float(quote["change_pct"]), threshold)


def get_stock_quote(stock_code: str):
    import yfinance as yf
    history = yf.Ticker(stock_code).history(period="1mo", interval="1d", auto_adjust=True)
    if history.empty:
        raise ValueError(f"No market data for {stock_code}")
    closes = history["Close"].dropna()
    if len(closes) < 2:
        raise ValueError(f"Insufficient market data for {stock_code}")
    previous, latest = float(closes.iloc[-2]), float(closes.iloc[-1])
    if not math.isfinite(previous) or previous <= 0 or not math.isfinite(latest):
        raise ValueError(f"Invalid close price for {stock_code}")
    return {"code": stock_code, "price": latest,
            "change_pct": (latest - previous) / previous * 100,
            "date": str(closes.index[-1].date())}


def send_discord(message: str):
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        raise ValueError("DISCORD_WEBHOOK_URL is not configured")
    request = urllib.request.Request(
        url, data=json.dumps({"content": message}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "StockRiskAlert/1.0"},
        method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"Discord returned HTTP {response.status}")


def process_quotes(quotes, threshold, send_enabled=False, state=None):
    """Check and (optionally) send once per stock/date; update state only after success."""
    state = state if state is not None else AlertState()
    results = {"alerts": 0, "sent": 0, "duplicates": 0}
    for quote in quotes:
        symbol, market_date = quote["code"], quote["date"]
        alert = check_risk_from_quote(quote, threshold)
        print(f"{symbol} ({market_date}): {quote['change_pct']:.2f}%")
        if not alert:
            print("No risk alert triggered.")
            continue
        results["alerts"] += 1
        if state.was_sent(symbol, market_date):
            results["duplicates"] += 1
            print(f"Already sent for {symbol} on {market_date}; skipping.")
            continue
        if not send_enabled:
            print("Risk detected; Discord disabled (state unchanged).")
            continue
        send_discord(f"{alert}\nData Date: {market_date}")
        state.mark_sent(symbol, market_date)
        results["sent"] += 1
        print("Discord risk alert sent successfully.")
    return results


def main():
    threshold = float(os.getenv("RISK_DROP_THRESHOLD", "5.0"))
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("RISK_DROP_THRESHOLD must be positive and finite")
    send_enabled = os.getenv("SEND_DISCORD", "false").lower() == "true"
    if os.getenv("WEBHOOK_TEST", "false").lower() == "true":
        if not send_enabled:
            raise ValueError("WEBHOOK_TEST requires SEND_DISCORD=true")
        send_discord("✅ Stock Risk Alert: Discord connection test successful.")
        print("Discord connection test successful.")
        return
    symbols = [s.strip().upper() for s in os.getenv("STOCK_CODES", "NVDA,AAPL,TSLA").split(",") if s.strip()]
    if not symbols:
        raise ValueError("STOCK_CODES cannot be empty")
    quotes, failures = [], []
    for symbol in dict.fromkeys(symbols):
        try:
            quotes.append(get_stock_quote(symbol))
        except Exception as exc:
            failures.append(symbol)
            print(f"Market data error for {symbol}: {exc}")
    summary = process_quotes(quotes, threshold, send_enabled)
    print(f"Summary: {summary}")
    if failures:
        raise RuntimeError("Market data failed for: " + ", ".join(failures))


if __name__ == "__main__":
    main()
